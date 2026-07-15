"""Grants test for the column-level Functions role migration (0051).

Creates the Functions role, runs the migration chain through the column-grant
narrowing, and asserts the role can SELECT the prepare/reconcile columns and
UPDATE only the result/lifecycle columns -- never the immutable
user/requirement/snapshot/submitted-value identity, and never INSERT/DELETE.
"""

from __future__ import annotations

import os
import uuid
from pathlib import Path

import pytest
from sqlalchemy import create_engine, text

MIGRATION_DB = "test_verification_attempt_grants"
_BEFORE = "0048_validate_deployment_architecture_type"
_HEAD = "0051_narrow_functions_role_attempt_grants"

_EXPECTED_UPDATE_COLUMNS = {
    "outcome",
    "error_code",
    "validation_message",
    "terminal_source",
    "feedback_json",
    "started_at",
    "completed_at",
    "updated_at",
}

_IMMUTABLE_COLUMNS = (
    "id",
    "user_id",
    "requirement_uuid",
    "requirement_snapshot",
    "requirement_snapshot_hash",
    "snapshot_source",
    "payload_version",
    "submission_value_kind",
    "submitted_value",
    "github_username_snapshot",
    "legacy_job_id",
)


def _sync_url() -> str:
    raw = os.environ.get(
        "DATABASE__URL",
        "******db:5432/learntocloud",
    )
    return raw.replace("+asyncpg", "+psycopg2")


def _admin_url() -> str:
    return _sync_url().rsplit("/", 1)[0] + "/postgres"


@pytest.fixture()
def alembic_config():
    from pytest_alembic.config import Config

    return Config(
        config_options={
            "file": str(Path(__file__).parent.parent / "alembic.ini"),
            "script_location": str(Path(__file__).parent.parent / "alembic"),
        },
    )


@pytest.fixture()
def alembic_engine():
    admin_eng = create_engine(_admin_url(), isolation_level="AUTOCOMMIT")
    with admin_eng.connect() as conn:
        conn.execute(
            text(
                "SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
                f"WHERE datname = '{MIGRATION_DB}' AND pid <> pg_backend_pid()"
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
                "SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
                f"WHERE datname = '{MIGRATION_DB}' AND pid <> pg_backend_pid()"
            )
        )
        conn.execute(text(f"DROP DATABASE IF EXISTS {MIGRATION_DB}"))
    admin_eng.dispose()


def test_functions_role_column_grants(alembic_runner, alembic_engine, monkeypatch):
    role = f"ltc_attempt_grant_{uuid.uuid4().hex[:10]}"
    monkeypatch.setenv("POSTGRES_VERIFICATION_FUNCTIONS_ROLE", role)

    try:
        alembic_runner.migrate_up_to(_BEFORE)

        admin = create_engine(_admin_url(), isolation_level="AUTOCOMMIT")
        with admin.connect() as conn:
            conn.execute(text(f'CREATE ROLE "{role}"'))
        admin.dispose()

        alembic_runner.migrate_up_to(_HEAD)

        with alembic_engine.connect() as conn:
            update_columns = set(
                conn.execute(
                    text(
                        """
                        SELECT column_name
                        FROM information_schema.column_privileges
                        WHERE grantee = :role
                          AND table_name = 'verification_attempts'
                          AND privilege_type = 'UPDATE'
                        """
                    ),
                    {"role": role},
                ).scalars()
            )

            # No table-level INSERT/DELETE/UPDATE at column-narrowed stage.
            table_grants = set(
                conn.execute(
                    text(
                        """
                        SELECT privilege_type
                        FROM information_schema.role_table_grants
                        WHERE grantee = :role
                          AND table_name = 'verification_attempts'
                        """
                    ),
                    {"role": role},
                ).scalars()
            )

            select_ok = conn.execute(
                text(
                    "SELECT has_column_privilege("
                    ":role, 'verification_attempts', 'submitted_value', 'SELECT')"
                ),
                {"role": role},
            ).scalar_one()

            immutable_update = {
                col: conn.execute(
                    text(
                        "SELECT has_column_privilege("
                        ":role, 'verification_attempts', :col, 'UPDATE')"
                    ),
                    {"role": role, "col": col},
                ).scalar_one()
                for col in _IMMUTABLE_COLUMNS
            }

        assert update_columns == _EXPECTED_UPDATE_COLUMNS
        assert "INSERT" not in table_grants
        assert "DELETE" not in table_grants
        assert select_ok is True
        assert not any(immutable_update.values()), immutable_update
    finally:
        admin = create_engine(_admin_url(), isolation_level="AUTOCOMMIT")
        with admin.connect() as conn:
            conn.execute(
                text(
                    "SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
                    f"WHERE datname = '{MIGRATION_DB}' AND pid <> pg_backend_pid()"
                )
            )
            conn.execute(text(f"DROP DATABASE IF EXISTS {MIGRATION_DB}"))
            conn.execute(text(f'DROP ROLE IF EXISTS "{role}"'))
        admin.dispose()
