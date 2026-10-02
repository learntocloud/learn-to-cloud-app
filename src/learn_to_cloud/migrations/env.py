"""Alembic environment.

Migrations run inside a dedicated Azure Container App Job
(``job-ltc-migrations-${env}``) defined in ``infra/migrations.tf``. The job
is configured with ``parallelism = 1``, ``replica_completion_count = 1``,
``replica_retry_limit = 0`` so exactly one process ever runs the upgrade.
Migrations are not invoked from the API container's startup path; the API
only verifies DB connectivity at boot.

That single-runner guarantee lets this env stay tiny:
no advisory lock dance, no race handling. If concurrency assumptions ever
change, restore the advisory lock pattern from git history (see PR #436 and
earlier).

Post-migration head verification is performed by
``learn_to_cloud.migrations.main`` via the upstream ``alembic.command.current(
config, check_heads=True)``. The original silent-failure bug (issue #432) is
still defended against because ``command.upgrade`` itself re-raises every
exception logged here.
"""

from __future__ import annotations

import asyncio
import logging
import os
import time
from importlib import import_module

from alembic import context
from azure.identity import DefaultAzureCredential
from sqlalchemy import URL, Connection, make_url
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine
from sqlalchemy.pool import NullPool

from learn_to_cloud.core.azure_auth import AZURE_PG_SCOPE
from learn_to_cloud.core.config import (
    get_migration_settings,
)
from learn_to_cloud.core.database import Base

# Import models so Base.metadata is populated for autogenerate.
import_module("learn_to_cloud.models")

config = context.config

# Only the ``alembic`` CLI sets cmd_opts. Programmatic callers (the migration
# job, tests) own logging; the CLI gets progress on stderr so ``--sql`` output
# on stdout stays clean.
if config.cmd_opts is not None:
    logging.basicConfig(format="%(levelname)-5.5s [%(name)s] %(message)s")
    logging.getLogger("alembic").setLevel(logging.INFO)

target_metadata = Base.metadata


def _get_azure_token_with_retry() -> str:
    """Return an Entra ID token for PostgreSQL with retry.

    Managed-identity sidecars can take up to ~30s to come up on Container
    Apps cold starts, so we retry a handful of times with exponential
    backoff before giving up.
    """
    max_attempts = 6
    initial_wait = 2

    client_id = os.environ.get("AZURE_CLIENT_ID")
    cred_kwargs: dict[str, str] = {}
    if client_id:
        cred_kwargs["managed_identity_client_id"] = client_id

    last_error: Exception | None = None
    for attempt in range(max_attempts):
        try:
            credential = DefaultAzureCredential(**cred_kwargs)
            return credential.get_token(AZURE_PG_SCOPE).token
        except Exception as e:
            last_error = e
            if attempt < max_attempts - 1:
                time.sleep(initial_wait * (2**attempt))

    raise RuntimeError(
        f"Failed to acquire Azure AD token after {max_attempts} attempts"
    ) from last_error


def _get_database_url(*, with_token: bool) -> URL:
    """Return an asyncpg URL; offline mode only needs the dialect."""
    settings = get_migration_settings().database
    if settings.use_azure_postgres:
        return URL.create(
            "postgresql+asyncpg",
            username=settings.user,
            password=_get_azure_token_with_retry() if with_token else None,
            host=settings.host,
            port=settings.port,
            database=settings.name,
            query={"ssl": "require"},
        )
    return make_url(settings.url)


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode (emit SQL, no DB connection)."""
    context.configure(
        url=_get_database_url(with_token=False),
        target_metadata=target_metadata,
        literal_binds=True,
        compare_type=True,
        compare_server_default=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def _do_run_migrations(connection: Connection) -> None:
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        compare_type=True,
        compare_server_default=True,
    )
    with context.begin_transaction():
        context.run_migrations()


async def _run_async_migrations(engine: AsyncEngine) -> None:
    async with engine.connect() as connection:
        await connection.run_sync(_do_run_migrations)
        await connection.commit()


def run_migrations_online() -> None:
    """Run migrations against a live PostgreSQL connection."""
    logger = logging.getLogger("alembic")

    # pytest-alembic injects an engine via config.attributes;
    # in production the migration job creates its own engine.
    engine: AsyncEngine | None = config.attributes.get("connection", None)
    owns_engine = engine is None
    if engine is None:
        engine = create_async_engine(
            _get_database_url(with_token=True), poolclass=NullPool
        )

    async def run_and_dispose() -> None:
        try:
            await _run_async_migrations(engine)
        finally:
            if owns_engine:
                await engine.dispose()

    try:
        asyncio.run(run_and_dispose())
    except Exception:
        # Always log so silent failures (e.g. swallowed by some future
        # exception handler) cannot ship green. See issue #432.
        logger.exception("alembic.migration.failed")
        raise


def run() -> None:
    if context.is_offline_mode():
        run_migrations_offline()
    else:
        run_migrations_online()


run()
