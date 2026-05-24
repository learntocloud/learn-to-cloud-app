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

# Re-export built-in tests so pytest discovers them.
__all__ = [
    "test_upgrade",
    "test_single_head_revision",
    "test_model_definitions_match_ddl",
    "test_up_down_consistency",
]


def _sync_url() -> str:
    raw = os.environ.get(
        "DATABASE_URL",
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
