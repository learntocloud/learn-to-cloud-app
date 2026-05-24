"""Standard migration tests powered by pytest-alembic.

Provides the standard suite of migration safety checks:
- upgrade: full chain from base to head succeeds
- model_definitions_match_ddl: models and migrations are in sync
- up_down_consistency: every downgrade succeeds
- single_head_revision: no branching history

Plus a custom regression test for the #432 incident pattern: ghost
verification_jobs rows that would violate a unique index.

See: https://github.com/learntocloud/learn-to-cloud-app/issues/439
"""

from __future__ import annotations

import os
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID

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


# ------------------------------------------------------------------ #
# Custom regression test: #432 ghost verification_jobs
# ------------------------------------------------------------------ #

_NOW = datetime.now(UTC)


@pytest.mark.migration_chain
def test_upgrade_with_prod_data_shapes(alembic_runner, alembic_engine):
    """Migration 0020 succeeds when ghost verification_jobs exist.

    Reproduces incident #432: duplicate (user_id, requirement_id)
    rows with result_submission_id IS NULL and terminal status would
    violate the new partial unique index unless 0020 cleans them up
    first.
    """
    # Migrate up to (but not including) the problematic migration
    alembic_runner.migrate_up_before("0020_add_result_submission_id_indexes")

    # Insert the prod-shaped data that caused #432
    with alembic_engine.begin() as conn:
        # Prerequisite: users
        conn.execute(
            text(
                "INSERT INTO users"
                " (id, github_username, is_admin,"
                " created_at, updated_at)"
                " VALUES"
                " (1001, 'alice', false, :now, :now),"
                " (1002, 'bob', false, :now, :now)"
            ),
            {"now": _NOW},
        )
        # Prerequisite: submissions (for FK on result_submission_id)
        conn.execute(
            text(
                "INSERT INTO submissions"
                " (id, user_id, requirement_id,"
                " submission_type, phase_id,"
                " submitted_value, is_validated,"
                " verification_completed,"
                " created_at, updated_at)"
                " VALUES"
                " (1, 1001, 'phase2-net',"
                " 'networking_token', 2,"
                " 'flag{x}', true, true, :now, :now)"
            ),
            {"now": _NOW},
        )
        # Ghost verification jobs: the #432 pattern
        # Two terminal-status jobs for the same (user, requirement)
        # with result_submission_id IS NULL
        conn.execute(
            text(
                "INSERT INTO verification_jobs"
                " (id, user_id, requirement_id, phase_id,"
                " submission_type, submitted_value,"
                " status, result_submission_id,"
                " created_at, updated_at)"
                " VALUES"
                " (:id1, 1001, 'phase1-gp', 1,"
                " 'github_profile', 'https://gh/a',"
                " 'failed', NULL, :now, :now),"
                " (:id2, 1001, 'phase1-gp', 1,"
                " 'github_profile', 'https://gh/a',"
                " 'server_error', NULL, :now, :now),"
                " (:id3, 1001, 'phase2-net', 2,"
                " 'networking_token', 'flag{x}',"
                " 'succeeded', 1, :now, :now),"
                " (:id4, 1002, 'phase1-gp', 1,"
                " 'github_profile', 'https://gh/b',"
                " 'queued', NULL, :now, :now)"
            ),
            {
                "now": _NOW,
                "id1": str(UUID("a0000000-0000-0000-0000-000000000001")),
                "id2": str(UUID("a0000000-0000-0000-0000-000000000002")),
                "id3": str(UUID("a0000000-0000-0000-0000-000000000003")),
                "id4": str(UUID("a0000000-0000-0000-0000-000000000004")),
            },
        )

    # Continue upgrading through 0020+ to head.
    # If 0020's cleanup DELETE is missing, this fails with
    # UniqueViolation on the partial unique index.
    alembic_runner.migrate_up_to("head")
