"""Populated session migration, retry, downgrade, and nonowner privilege tests."""

from io import StringIO
from pathlib import Path
from uuid import UUID, uuid4

import pytest
from alembic.config import Config
from learn_to_cloud_shared.models import AuthSession, LearnerStepCompletion, User
from sqlalchemy import delete, func, insert, inspect, select, text
from sqlalchemy.exc import IntegrityError

from alembic import command, op
from tests.test_migration_chain import alembic_config as alembic_config
from tests.test_migration_chain import alembic_engine as alembic_engine

BASE = "0059_drop_user_legacy_names"
TABLE = "0060_add_auth_sessions"
HEAD = "0061_auth_sessions_concurrent_indexes"


def seed_account(conn):
    conn.execute(insert(User).values(id=1, github_username="preserved"))
    conn.execute(insert(LearnerStepCompletion).values(user_id=1, step_uuid=UUID(int=1)))


def insert_session(conn, digest=b"a" * 32):
    now = func.statement_timestamp()
    conn.execute(
        insert(AuthSession).values(
            token_digest=digest,
            user_id=1,
            created_at=now,
            updated_at=now,
            last_seen_at=now,
            expires_at=now + text("interval '30 days'"),
        )
    )


def test_populated_upgrade_downgrade_and_reupgrade(alembic_runner, alembic_engine):
    alembic_runner.migrate_up_to(BASE)
    with alembic_engine.begin() as conn:
        seed_account(conn)
        users = conn.execute(select(User.__table__)).all()
        progress = conn.execute(select(LearnerStepCompletion.__table__)).all()
    alembic_runner.migrate_up_to(HEAD)
    with alembic_engine.begin() as conn:
        assert conn.execute(select(User.__table__)).all() == users
        assert conn.execute(select(LearnerStepCompletion.__table__)).all() == progress
        assert conn.execute(select(func.count()).select_from(AuthSession)).scalar() == 0
        indexes = {i["name"]: i for i in inspect(conn).get_indexes("auth_sessions")}
        assert set(indexes) == {
            "ix_auth_sessions_user_id",
            "ix_auth_sessions_expires_at",
            "ix_auth_sessions_last_seen_at",
        }
        fk = inspect(conn).get_foreign_keys("auth_sessions")
        assert len(fk) == 1
        assert fk[0]["referred_table"] == "users"
        assert fk[0]["options"]["ondelete"] == "CASCADE"
        insert_session(conn)
    alembic_runner.migrate_down_to(BASE)
    with alembic_engine.connect() as conn:
        assert "auth_sessions" not in inspect(conn).get_table_names()
        assert conn.execute(select(User.__table__)).all() == users
        assert conn.execute(select(LearnerStepCompletion.__table__)).all() == progress
    alembic_runner.migrate_up_to(HEAD)
    with alembic_engine.begin() as conn:
        assert conn.execute(select(func.count()).select_from(AuthSession)).scalar() == 0
        insert_session(conn)
        conn.execute(delete(User).where(User.id == 1))
        assert conn.execute(select(func.count()).select_from(AuthSession)).scalar() == 0


def test_concurrent_index_failure_retry_rebuilds_invalid_indexes(
    alembic_runner, alembic_engine, monkeypatch
):
    alembic_runner.migrate_up_to(TABLE)
    with alembic_engine.begin() as conn:
        seed_account(conn)
        insert_session(conn)
        insert_session(conn, b"b" * 32)
    with alembic_engine.connect().execution_options(
        isolation_level="AUTOCOMMIT"
    ) as conn:
        with pytest.raises(IntegrityError):
            conn.execute(
                text(
                    "CREATE UNIQUE INDEX CONCURRENTLY ix_auth_sessions_user_id "
                    "ON auth_sessions (user_id)"
                )
            )
        assert (
            conn.execute(
                text(
                    "SELECT indisvalid FROM pg_index "
                    "WHERE indexrelid = 'ix_auth_sessions_user_id'::regclass"
                )
            ).scalar_one()
            is False
        )

    original = op.execute

    def fail_second_index(statement, *args, **kwargs):
        if str(statement).startswith(
            "CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_auth_sessions_expires_at"
        ):
            raise RuntimeError("Simulated interrupted index build")
        return original(statement, *args, **kwargs)

    with monkeypatch.context() as patch:
        patch.setattr(op, "execute", fail_second_index)
        with pytest.raises(RuntimeError, match="Simulated"):
            alembic_runner.migrate_up_to(HEAD)
    with alembic_engine.connect() as conn:
        assert (
            conn.execute(text("SELECT version_num FROM alembic_version")).scalar_one()
            == TABLE
        )
        assert conn.execute(select(func.count()).select_from(AuthSession)).scalar() == 2
    alembic_runner.migrate_up_to(HEAD)
    with alembic_engine.connect() as conn:
        validity = conn.execute(
            text(
                "SELECT indisvalid, indisready, indisunique FROM pg_index "
                "JOIN pg_class ON pg_class.oid = indexrelid "
                "WHERE relname LIKE 'ix_auth_sessions_%'"
            )
        ).all()
        assert validity == [(True, True, False)] * 3


@pytest.mark.parametrize("grant_mode", ["default_acl", "explicit"])
def test_api_runtime_dml_without_ownership_or_functions_access(
    alembic_runner, alembic_engine, monkeypatch, grant_mode
):
    runtime = f"session_api_{uuid4().hex[:12]}"
    functions = f"session_fn_{uuid4().hex[:12]}"
    if grant_mode == "explicit":
        monkeypatch.setenv("POSTGRES_API_RUNTIME_ROLE", runtime)
    else:
        monkeypatch.delenv("POSTGRES_API_RUNTIME_ROLE", raising=False)
    monkeypatch.setenv("POSTGRES_VERIFICATION_FUNCTIONS_ROLE", functions)
    try:
        with alembic_engine.begin() as conn:
            conn.execute(text(f'CREATE ROLE "{runtime}"'))
            if grant_mode == "default_acl":
                conn.execute(
                    text(
                        "ALTER DEFAULT PRIVILEGES IN SCHEMA public "
                        f'GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO "{runtime}"'
                    )
                )
        alembic_runner.migrate_up_to(BASE)
        with alembic_engine.begin() as conn:
            conn.execute(text(f'CREATE ROLE "{functions}"'))
            seed_account(conn)
            conn.execute(text(f'GRANT USAGE ON SCHEMA public TO "{runtime}"'))
            conn.execute(text(f'GRANT SELECT, UPDATE ON users TO "{runtime}"'))
        alembic_runner.migrate_up_to(HEAD)
        with alembic_engine.begin() as conn:
            privileges = set(
                conn.execute(
                    text(
                        "SELECT privilege_type "
                        "FROM information_schema.table_privileges "
                        "WHERE table_name = 'auth_sessions' AND grantee = :role"
                    ),
                    {"role": runtime},
                ).scalars()
            )
            assert privileges == {"SELECT", "INSERT", "UPDATE", "DELETE"}
            assert (
                conn.execute(
                    text(
                        "SELECT has_table_privilege(:role, 'auth_sessions', "
                        "'SELECT,INSERT,UPDATE,DELETE')"
                    ),
                    {"role": functions},
                ).scalar_one()
                is False
            )
            assert (
                conn.execute(
                    text(
                        "SELECT pg_get_userbyid(relowner) FROM pg_class "
                        "WHERE oid = 'auth_sessions'::regclass"
                    )
                ).scalar_one()
                != runtime
            )
            conn.execute(text(f'SET LOCAL ROLE "{runtime}"'))
            conn.execute(text("SELECT id FROM users WHERE id = 1 FOR UPDATE"))
            insert_session(conn)
            assert conn.execute(select(AuthSession.user_id)).scalar_one() == 1
            conn.execute(
                text("UPDATE auth_sessions SET last_seen_at = statement_timestamp()")
            )
            conn.execute(text("DELETE FROM auth_sessions"))
            assert (
                conn.execute(select(func.count()).select_from(AuthSession)).scalar()
                == 0
            )
    finally:
        with alembic_engine.begin() as conn:
            for role in (runtime, functions):
                conn.execute(text(f'DROP OWNED BY "{role}"'))
                conn.execute(text(f'DROP ROLE "{role}"'))


def test_offline_session_ddl_has_atomic_stamp_and_bounded_concurrent_indexes():
    config = Config(str(Path(__file__).parent.parent / "alembic.ini"))
    config.set_main_option(
        "script_location", str(Path(__file__).parent.parent / "alembic")
    )
    output = StringIO()
    config.output_buffer = output
    command.upgrade(config, f"{BASE}:{HEAD}", sql=True)
    sql = output.getvalue()
    table = sql.index("CREATE TABLE auth_sessions")
    stamp = sql.index(f"SET version_num='{TABLE}'")
    commit = sql.index("COMMIT;", stamp)
    index = sql.index("CREATE INDEX CONCURRENTLY")
    assert table < stamp < commit < index
    assert "SET LOCAL lock_timeout = '5s';" in sql
    assert "SET LOCAL statement_timeout = '2min';" in sql
    assert "SET statement_timeout = '10min';" in sql
    assert "RESET statement_timeout;" in sql
    assert sql.count("DROP INDEX CONCURRENTLY IF EXISTS ix_auth_sessions_") == 3
    assert sql.count("CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_auth_sessions_") == 3
    output = StringIO()
    config.output_buffer = output
    command.downgrade(config, f"{HEAD}:{BASE}", sql=True)
    sql = output.getvalue()
    assert sql.rindex("DROP INDEX CONCURRENTLY") < sql.index("DROP TABLE auth_sessions")
