"""Test that the full alembic migration chain works with prod-like data.

Stamps the database to an intermediate revision, loads fixture data that
reproduces real-world edge cases (e.g. ghost verification jobs from
incident #432), then runs ``alembic upgrade head`` and verifies it
succeeds.  The fixture file is append-only: each time a new prod data
shape causes a migration failure, the fix PR adds INSERTs to the
fixture so CI catches regressions permanently.

See: https://github.com/learntocloud/learn-to-cloud-app/issues/439
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest
from sqlalchemy import create_engine, text

STAMP_REVISION = "0019_enforce_not_null_columns"
FIXTURE_PATH = Path(__file__).parent / "fixtures" / "migration_data_shapes.sql"
API_DIR = str(Path(__file__).parent.parent)
MIGRATION_DB = "test_migration_chain"


def _build_sync_url() -> str:
    """Derive a psycopg2 URL from the DATABASE_URL env var."""
    raw = os.environ.get(
        "DATABASE_URL",
        "postgresql+asyncpg://postgres:postgres@db:5432/learntocloud",
    )
    return raw.replace("+asyncpg", "+psycopg2")


def _admin_url(sync_url: str) -> str:
    return sync_url.rsplit("/", 1)[0] + "/postgres"


def _migration_url(sync_url: str) -> str:
    return sync_url.rsplit("/", 1)[0] + f"/{MIGRATION_DB}"


def _drop_db(admin_engine, db_name: str) -> None:  # type: ignore[no-any-explicit]
    """Terminate connections then drop the database."""
    with admin_engine.connect() as conn:
        conn.execute(
            text(
                "SELECT pg_terminate_backend(pid) "
                "FROM pg_stat_activity "
                f"WHERE datname = '{db_name}' "
                "AND pid <> pg_backend_pid()"
            )
        )
        conn.execute(text(f"DROP DATABASE IF EXISTS {db_name}"))


def _run_alembic(*args: str, env: dict[str, str]) -> subprocess.CompletedProcess[str]:
    """Run an alembic command via subprocess for full isolation."""
    return subprocess.run(
        [sys.executable, "-m", "alembic", *args],
        cwd=API_DIR,
        env=env,
        capture_output=True,
        text=True,
        timeout=120,
    )


@pytest.mark.migration_chain
def test_upgrade_head_with_prod_data_shapes() -> None:
    """Full chain upgrade succeeds against realistic prod data."""
    sync_url = _build_sync_url()
    admin_eng = create_engine(_admin_url(sync_url), isolation_level="AUTOCOMMIT")
    mig_url = _migration_url(sync_url)

    try:
        # Create a fresh database for this test
        _drop_db(admin_eng, MIGRATION_DB)
        with admin_eng.connect() as conn:
            conn.execute(text(f"CREATE DATABASE {MIGRATION_DB}"))

        # Build env for subprocess (don't mutate os.environ)
        sub_env = {
            **os.environ,
            "DATABASE_URL": mig_url.replace("+psycopg2", "+asyncpg"),
        }

        # Upgrade to the stamp revision
        result = _run_alembic("upgrade", STAMP_REVISION, env=sub_env)
        assert result.returncode == 0, (
            f"Stamp to {STAMP_REVISION} failed:\n{result.stderr}"
        )

        # Load fixture data
        fixture_sql = FIXTURE_PATH.read_text()
        engine = create_engine(mig_url)
        try:
            with engine.begin() as conn:
                conn.exec_driver_sql(fixture_sql)
        finally:
            engine.dispose()

        # Run the remaining migrations -- this is the actual test
        result = _run_alembic("upgrade", "head", env=sub_env)
        assert result.returncode == 0, f"Migration to head failed:\n{result.stderr}"

    finally:
        admin_eng = create_engine(_admin_url(sync_url), isolation_level="AUTOCOMMIT")
        _drop_db(admin_eng, MIGRATION_DB)
        admin_eng.dispose()


@pytest.mark.migration_chain
def test_downgrade_and_reupgrade() -> None:
    """Downgrade one revision then re-upgrade succeeds."""
    sync_url = _build_sync_url()
    admin_eng = create_engine(_admin_url(sync_url), isolation_level="AUTOCOMMIT")
    mig_url = _migration_url(sync_url)

    try:
        _drop_db(admin_eng, MIGRATION_DB)
        with admin_eng.connect() as conn:
            conn.execute(text(f"CREATE DATABASE {MIGRATION_DB}"))

        sub_env = {
            **os.environ,
            "DATABASE_URL": mig_url.replace("+psycopg2", "+asyncpg"),
        }

        # Full upgrade first
        result = _run_alembic("upgrade", "head", env=sub_env)
        assert result.returncode == 0, f"Initial upgrade failed:\n{result.stderr}"

        # Downgrade one revision
        result = _run_alembic("downgrade", "-1", env=sub_env)
        assert result.returncode == 0, f"Downgrade failed:\n{result.stderr}"

        # Re-upgrade to head
        result = _run_alembic("upgrade", "head", env=sub_env)
        assert result.returncode == 0, f"Re-upgrade failed:\n{result.stderr}"

    finally:
        admin_eng = create_engine(_admin_url(sync_url), isolation_level="AUTOCOMMIT")
        _drop_db(admin_eng, MIGRATION_DB)
        admin_eng.dispose()
