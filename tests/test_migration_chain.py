"""Standard migration tests powered by pytest-alembic.

Provides the standard suite of migration safety checks:
- upgrade: full chain from base to head succeeds
- model_definitions_match_ddl: models and migrations are in sync
- up_down_consistency: every downgrade succeeds
- single_head_revision: no branching history

See: https://github.com/learntocloud/learn-to-cloud-app/issues/439
"""

from __future__ import annotations

import asyncio
import os

import asyncpg
import pytest
from pytest_alembic.config import Config as PytestAlembicConfig
from pytest_alembic.tests import (
    test_model_definitions_match_ddl,
    test_single_head_revision,
    test_up_down_consistency,
    test_upgrade,
)
from sqlalchemy import make_url
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.pool import NullPool

from learn_to_cloud import migrations

MIGRATION_DB = "test_alembic_migrations"

# Re-export built-in tests so pytest discovers them.
__all__ = [
    "test_upgrade",
    "test_single_head_revision",
    "test_model_definitions_match_ddl",
    "test_up_down_consistency",
]


def _base_url():
    return make_url(
        os.environ.get(
            "DATABASE__URL",
            "postgresql+asyncpg://postgres:postgres@127.0.0.1:55432/learntocloud",
        )
    )


async def _recreate_migration_db(*, create: bool) -> None:
    url = _base_url()
    conn = await asyncpg.connect(
        user=url.username,
        password=url.password,
        host=url.host,
        port=url.port,
        database="postgres",
    )
    try:
        await conn.execute(
            "SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
            "WHERE datname = $1 AND pid <> pg_backend_pid()",
            MIGRATION_DB,
        )
        await conn.execute(f"DROP DATABASE IF EXISTS {MIGRATION_DB}")
        if create:
            await conn.execute(f"CREATE DATABASE {MIGRATION_DB}")
    finally:
        await conn.close()


# ------------------------------------------------------------------ #
# pytest-alembic fixtures
# ------------------------------------------------------------------ #


@pytest.fixture()
def alembic_config():
    """Point pytest-alembic at the packaged migration scripts."""

    return PytestAlembicConfig(
        config_options={"script_location": migrations.SCRIPT_LOCATION},
    )


@pytest.fixture()
def alembic_engine():
    """Provide a clean, dedicated database for migration tests.

    NullPool keeps connections from leaking across the event loops that
    pytest-alembic and env.py each create with ``asyncio.run``.
    """
    asyncio.run(_recreate_migration_db(create=True))
    engine = create_async_engine(
        _base_url().set(database=MIGRATION_DB), poolclass=NullPool
    )
    yield engine
    asyncio.run(engine.dispose())
    asyncio.run(_recreate_migration_db(create=False))
