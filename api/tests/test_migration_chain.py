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
from pathlib import Path

import pytest
from pytest_alembic.tests import (
    test_model_definitions_match_ddl,
    test_single_head_revision,
    test_up_down_consistency,
    test_upgrade,
)
from sqlalchemy import create_engine, text

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
        "postgresql+asyncpg://postgres:postgres@db:5432/learntocloud",
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
