"""Standard migration tests powered by pytest-alembic.

Provides the standard suite of migration safety checks:
- upgrade: full chain from base to head succeeds
- model_definitions_match_ddl: models and migrations are in sync
- up_down_consistency: every downgrade succeeds
- single_head_revision: no branching history

See: https://github.com/learntocloud/learn-to-cloud-app/issues/439
"""

from __future__ import annotations

import os
from datetime import UTC, datetime
from io import StringIO
from pathlib import Path
from unittest.mock import AsyncMock, patch
from uuid import UUID

import pytest
from alembic.config import Config
from learn_to_cloud_shared.models import LearnerStepCompletion, User
from learn_to_cloud_shared.repositories.user_repository import UserRepository
from pytest_alembic.tests import (
    test_model_definitions_match_ddl,
    test_single_head_revision,
    test_up_down_consistency,
    test_upgrade,
)
from sqlalchemy import Text, create_engine, event, inspect, select, text
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

from alembic import command

MIGRATION_DB = "test_alembic_migrations"
os.environ.setdefault(
    "POSTGRES_VERIFICATION_FUNCTIONS_ROLE",
    "ltc_verification_functions_dev",
)

# Re-export built-in tests so pytest discovers them.
__all__ = [
    "test_upgrade",
    "test_single_head_revision",
    "test_model_definitions_match_ddl",
    "test_up_down_consistency",
]


def _sync_url() -> str:
    raw = os.environ.get(
        "DATABASE__URL",
        "postgresql+asyncpg://postgres:postgres@127.0.0.1:55432/learntocloud",
    )
    return raw.replace("+asyncpg", "+psycopg2")


def _admin_url() -> str:
    return _sync_url().rsplit("/", 1)[0] + "/postgres"


# ------------------------------------------------------------------ #
# pytest-alembic fixtures
# ------------------------------------------------------------------ #


@pytest.fixture()
def alembic_config():
    """Point pytest-alembic at our alembic.ini."""
    from pytest_alembic.config import Config

    return Config(
        config_options={
            "file": str(Path(__file__).parent.parent / "alembic.ini"),
            "script_location": str(Path(__file__).parent.parent / "alembic"),
        },
    )


@pytest.fixture()
def alembic_engine():
    """Provide a clean, dedicated database for migration tests."""
    admin_eng = create_engine(_admin_url(), isolation_level="AUTOCOMMIT")

    with admin_eng.connect() as conn:
        conn.execute(
            text(
                "SELECT pg_terminate_backend(pid) "
                "FROM pg_stat_activity "
                f"WHERE datname = '{MIGRATION_DB}' "
                "AND pid <> pg_backend_pid()"
            )
        )
        conn.execute(text(f"DROP DATABASE IF EXISTS {MIGRATION_DB}"))
        conn.execute(text(f"CREATE DATABASE {MIGRATION_DB}"))
    admin_eng.dispose()
    mig_url = _sync_url().rsplit("/", 1)[0] + f"/{MIGRATION_DB}"
    engine = create_engine(mig_url)
    yield engine
    engine.dispose()

    admin_eng = create_engine(_admin_url(), isolation_level="AUTOCOMMIT")
    with admin_eng.connect() as conn:
        conn.execute(
            text(
                "SELECT pg_terminate_backend(pid) "
                "FROM pg_stat_activity "
                f"WHERE datname = '{MIGRATION_DB}' "
                "AND pid <> pg_backend_pid()"
            )
        )
        conn.execute(text(f"DROP DATABASE IF EXISTS {MIGRATION_DB}"))
    admin_eng.dispose()


def test_contract_removes_legacy_database_objects(
    alembic_runner, alembic_engine
) -> None:
    alembic_runner.migrate_up_to("0055_drop_legacy_curriculum_contract")

    dropped_tables = {
        "verification_jobs",
        "submissions",
        "step_progress",
        "requirements",
        "learning_objectives",
        "steps",
        "topics",
        "phases",
    }
    with alembic_engine.connect() as conn:
        remaining_tables = set(
            conn.execute(
                text(
                    """
                    SELECT table_name
                    FROM information_schema.tables
                    WHERE table_schema = 'public'
                    """
                )
            ).scalars()
        )
        attempt_columns = set(
            conn.execute(
                text(
                    """
                    SELECT column_name
                    FROM information_schema.columns
                    WHERE table_schema = 'public'
                      AND table_name = 'verification_attempts'
                    """
                )
            ).scalars()
        )
        temporary_functions = set(
            conn.execute(
                text(
                    """
                    SELECT proname
                    FROM pg_proc
                    WHERE proname IN (
                        'mirror_step_progress_to_completions',
                        'bridge_legacy_verification_job_to_attempt',
                        'terminalize_deleted_legacy_verification_job'
                    )
                    """
                )
            ).scalars()
        )

    assert dropped_tables.isdisjoint(remaining_tables)
    assert "legacy_job_id" not in attempt_columns
    assert "legacy_submission_id" not in attempt_columns
    assert temporary_functions == set()


def test_head_removes_unused_attempt_traceparent(
    alembic_runner, alembic_engine
) -> None:
    alembic_runner.migrate_up_to("0057_drop_verification_attempt_traceparent")

    with alembic_engine.connect() as conn:
        attempt_columns = set(
            conn.execute(
                text(
                    """
                    SELECT column_name
                    FROM information_schema.columns
                    WHERE table_schema = 'public'
                      AND table_name = 'verification_attempts'
                    """
                )
            ).scalars()
        )

    assert "traceparent" not in attempt_columns


_PRE_DISPLAY_NAME = "0057_drop_verification_attempt_traceparent"
_DISPLAY_NAME_EXPANSION = "0058_add_user_display_name"
_LEGACY_USER_COLUMNS = (
    "id, first_name, last_name, avatar_url, github_username, "
    "is_admin, created_at, updated_at"
)
_WHITESPACE_CODEPOINTS = (
    *range(0x09, 0x0E),
    *range(0x1C, 0x21),
    0x85,
    0xA0,
    0x1680,
    *range(0x2000, 0x200B),
    0x2028,
    0x2029,
    0x202F,
    0x205F,
    0x3000,
)


def test_display_name_offline_sql_is_atomic_and_bounded() -> None:
    config = Config(str(Path(__file__).parent.parent / "alembic.ini"))
    config.set_main_option(
        "script_location", str(Path(__file__).parent.parent / "alembic")
    )
    upgrade_sql = StringIO()
    config.output_buffer = upgrade_sql
    command.upgrade(config, f"{_PRE_DISPLAY_NAME}:{_DISPLAY_NAME_EXPANSION}", sql=True)
    downgrade_sql = StringIO()
    config.output_buffer = downgrade_sql
    command.downgrade(
        config, f"{_DISPLAY_NAME_EXPANSION}:{_PRE_DISPLAY_NAME}", sql=True
    )

    for sql in (upgrade_sql.getvalue(), downgrade_sql.getvalue()):
        assert sql.count("BEGIN;") == sql.count("COMMIT;") == 1
        assert "SET LOCAL lock_timeout = '5s';" in sql
        assert "SET LOCAL statement_timeout = '2min';" in sql
        assert sql.index("SET LOCAL statement_timeout") < sql.index("ALTER TABLE users")
    assert "ADD COLUMN display_name TEXT" in upgrade_sql.getvalue()
    assert "UPDATE users" in upgrade_sql.getvalue()
    assert "DROP COLUMN display_name" in downgrade_sql.getvalue()
    assert "UPDATE users" not in downgrade_sql.getvalue()


def test_display_name_populated_upgrade_and_loss_aware_downgrade(
    alembic_runner, alembic_engine
) -> None:
    alembic_runner.migrate_up_to(_PRE_DISPLAY_NAME)
    cases = [
        (None, None, None),
        ("", "", None),
        ("Ada", None, "Ada"),
        (None, "Lovelace", "Lovelace"),
        ("Ada", "Lovelace", "Ada Lovelace"),
        ("", "Lovelace", "Lovelace"),
        ("Ada", "", "Ada"),
        (" \t\n", "\r\u2003\u3000", None),
        ("  Ada  ", " van  Rossum\t", "  Ada    van  Rossum\t"),
        ("李", "小龍", "李 小龍"),
        ("e\u0301", "👩🏽‍💻", "e\u0301 👩🏽‍💻"),
        ("A", None, "A"),
        ("a" * 255, "b" * 255, "a" * 255 + " " + "b" * 255),
        ("\u200b", "\ufeff", "\u200b \ufeff"),
    ]
    for codepoint in _WHITESPACE_CODEPOINTS:
        char = chr(codepoint)
        cases.extend(
            [
                (char, None, None),
                (None, char, None),
                (char, char, None),
                (char, "Name", "Name"),
                ("Name", char, "Name"),
                (f"{char}Name{char}", None, f"{char}Name{char}"),
            ]
        )

    created_at = datetime(2024, 1, 2, 3, 4, 5, tzinfo=UTC)
    updated_at = datetime(2025, 2, 3, 4, 5, 6, tzinfo=UTC)
    with alembic_engine.begin() as conn:
        conn.execute(
            text(
                f"INSERT INTO users ({_LEGACY_USER_COLUMNS}) "
                "VALUES (:id, :first_name, :last_name, :avatar_url, "
                ":github_username, :is_admin, :created_at, :updated_at)"
            ),
            [
                {
                    "id": user_id,
                    "first_name": first,
                    "last_name": last,
                    "avatar_url": f"https://example.com/{user_id}.png",
                    "github_username": f"migration-user-{user_id}",
                    "is_admin": user_id % 2 == 0,
                    "created_at": created_at,
                    "updated_at": updated_at,
                }
                for user_id, (first, last, _) in enumerate(cases, start=1000)
            ],
        )
        conn.execute(
            text(
                "INSERT INTO learner_step_completions "
                "(user_id, step_uuid, completed_at) "
                "VALUES (:user_id, :step_uuid, :completed_at)"
            ),
            [
                {
                    "user_id": user_id,
                    "step_uuid": UUID(int=user_id),
                    "completed_at": created_at,
                }
                for user_id in range(1000, 1000 + len(cases))
            ],
        )
        before_users = conn.execute(
            text(f"SELECT {_LEGACY_USER_COLUMNS} FROM users ORDER BY id")
        ).all()
        before_progress = conn.execute(
            text("SELECT * FROM learner_step_completions ORDER BY user_id")
        ).all()
        before_grants = conn.execute(
            text("SELECT relacl FROM pg_class WHERE oid = 'users'::regclass")
        ).scalar_one()

    for cycle in range(2):
        alembic_runner.migrate_up_to(_DISPLAY_NAME_EXPANSION)
        with alembic_engine.begin() as conn:
            columns = {c["name"]: c for c in inspect(conn).get_columns("users")}
            assert isinstance(columns["display_name"]["type"], Text)
            assert columns["display_name"]["nullable"] is True
            assert columns["display_name"]["default"] is None
            assert conn.execute(
                text("SELECT display_name FROM users ORDER BY id")
            ).scalars().all() == [expected for _, _, expected in cases]
            assert (
                conn.execute(
                    text(f"SELECT {_LEGACY_USER_COLUMNS} FROM users ORDER BY id")
                ).all()
                == before_users
            )
            assert (
                conn.execute(
                    text("SELECT * FROM learner_step_completions ORDER BY user_id")
                ).all()
                == before_progress
            )
            assert (
                conn.execute(
                    text("SELECT relacl FROM pg_class WHERE oid = 'users'::regclass")
                ).scalar_one()
                == before_grants
            )

            if cycle == 0:
                conn.execute(
                    text(
                        "UPDATE users SET display_name = 'Refreshed canonical name' "
                        "WHERE id = 1000"
                    )
                )

        if cycle == 0:
            alembic_runner.migrate_down_to(_PRE_DISPLAY_NAME)
            with alembic_engine.connect() as conn:
                assert "display_name" not in {
                    c["name"] for c in inspect(conn).get_columns("users")
                }
                assert (
                    conn.execute(
                        text(f"SELECT {_LEGACY_USER_COLUMNS} FROM users ORDER BY id")
                    ).all()
                    == before_users
                )
                assert (
                    conn.execute(
                        text("SELECT * FROM learner_step_completions ORDER BY user_id")
                    ).all()
                    == before_progress
                )


@pytest.mark.parametrize("revision", [_PRE_DISPLAY_NAME, _DISPLAY_NAME_EXPANSION])
async def test_display_name_expansion_runtime_compatibility(
    alembic_runner, alembic_engine, revision
) -> None:
    """Execute real ORM SQL on both rollout schemas, not standalone compilation."""
    alembic_runner.migrate_up_to(_PRE_DISPLAY_NAME)
    with alembic_engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO users "
                "(id, github_username, first_name, last_name, is_admin, "
                "created_at, updated_at) VALUES "
                "(7004, 'stored', 'Stored', 'Legacy', true, :now, :now)"
            ),
            {"now": datetime(2024, 1, 1, tzinfo=UTC)},
        )
    alembic_runner.migrate_up_to(revision)
    assert "display_name" in User.__table__.c
    assert "display_name" not in inspect(User).column_attrs
    async_engine = create_async_engine(
        alembic_engine.url.set(drivername="postgresql+asyncpg")
    )
    statements: list[str] = []

    def record_statement(conn, cursor, statement, parameters, context, executemany):
        statements.append(statement.lower())

    event.listen(async_engine.sync_engine, "before_cursor_execute", record_statement)
    try:
        async with AsyncSession(
            async_engine, autoflush=False, expire_on_commit=False
        ) as db:
            repo = UserRepository(db)
            created = await repo.get_or_create(
                7001, github_username="legacy", first_name="First", last_name="Last"
            )
            assert isinstance(created, User)
            assert (created.first_name, created.last_name) == ("First", "Last")
            existing = await repo.get_or_create(
                7001, github_username="ignored", first_name="Ignored"
            )
            assert existing is created
            assert existing.github_username == "legacy"
            assert existing.first_name == "First"

            inserted = await repo.upsert(
                7002, github_username="inserted", first_name="Original"
            )
            assert isinstance(inserted, User)
            created_at = inserted.created_at
            updated_at = inserted.updated_at
            db.expunge(inserted)
            updated = await repo.upsert(
                7002,
                github_username="updated",
                first_name="Updated",
                last_name="Profile",
                avatar_url="https://example.com/updated.png",
            )
            assert isinstance(updated, User)
            assert (updated.id, updated.github_username) == (7002, "updated")
            assert (updated.first_name, updated.last_name) == ("Updated", "Profile")
            assert updated.avatar_url == "https://example.com/updated.png"
            assert updated.created_at == created_at
            assert updated.updated_at > updated_at
            db.expunge(updated)
            cleared = await repo.upsert(7002, github_username="updated")
            assert (cleared.first_name, cleared.last_name, cleared.avatar_url) == (
                None,
                None,
                None,
            )
            stored = await repo.upsert(
                7004, github_username="stored", first_name="Later", last_name="Write"
            )
            assert (stored.first_name, stored.last_name) == ("Later", "Write")
            assert stored.is_admin is True
            assert stored.created_at == datetime(2024, 1, 1, tzinfo=UTC)

            normal = User(id=7003, github_username="normal", first_name="Normal")
            db.add(normal)
            await db.flush()
            normal.last_name = "Write"
            await db.flush()
            assert await repo.get_by_id(7003) is normal
            assert set(u.id for u in await repo.get_by_ids([7001, 7002, 7003])) == {
                7001,
                7002,
                7003,
            }
            assert await repo.get_by_ids([]) == []
            assert await repo.get_by_id(7999) is None
            assert await repo.count() == 4

            # Force the initial lookup miss of a concurrent insert, then execute
            # the real ON CONFLICT DO NOTHING RETURNING and fallback SELECT.
            start = len(statements)
            with patch.object(repo, "get_by_id", AsyncMock(return_value=None)):
                raced = await repo.get_or_create(
                    7003, github_username="ignored", first_name="Ignored"
                )
            assert raced is normal
            assert raced.github_username == "normal"
            assert raced.first_name == "Normal"
            assert "on conflict (id) do nothing returning" in statements[start]
            assert statements[start + 1].startswith("select ")

            db.add(
                LearnerStepCompletion(
                    user_id=7003, step_uuid=UUID(int=7003), completed_at=created_at
                )
            )
            await db.commit()
            db.expunge_all()
            selected = (
                await db.execute(select(User).where(User.id == 7003))
            ).scalar_one()
            assert (selected.first_name, selected.last_name) == ("Normal", "Write")
            await repo.delete(7003)
            assert await repo.get_by_id(7003) is None
            assert await db.scalar(select(LearnerStepCompletion.user_id)) is None
            assert await repo.count() == 3
            await db.commit()
    finally:
        event.remove(
            async_engine.sync_engine, "before_cursor_execute", record_statement
        )
        await async_engine.dispose()

    assert statements
    assert all("display_name" not in statement for statement in statements)
    assert any("on conflict (id) do update" in statement for statement in statements)
    assert any(
        statement.startswith("insert into users") and "returning" not in statement
        for statement in statements
    )
    if revision == _DISPLAY_NAME_EXPANSION:
        with alembic_engine.connect() as conn:
            assert conn.execute(
                text("SELECT display_name FROM users ORDER BY id")
            ).scalars().all() == [None, None, "Stored Legacy"]
