"""Alembic environment.

Migrations run inside a dedicated Azure Container App Job
(``job-ltc-migrations-${env}``) defined in ``infra/migrations.tf``. The job
is configured with ``parallelism = 1``, ``replica_completion_count = 1``,
``replica_retry_limit = 0`` so exactly one process ever runs the upgrade.
Migrations are not invoked from the API container's startup path; the API
only verifies DB connectivity at boot.

That single-runner guarantee lets this env stay tiny:
no advisory lock dance, no background-thread asyncio workarounds, no race
handling. If concurrency assumptions ever change, restore the advisory
lock pattern from git history (see PR #436 and earlier).

Post-migration head verification is performed by
``scripts/run_migrations.py`` via the upstream ``alembic.command.current(
config, check_heads=True)``; this env.py no longer carries a custom
``_verify_schema_at_head`` check. The original silent-failure bug (issue
#432) is still defended against because ``command.upgrade`` itself
re-raises every exception logged here.
"""

from __future__ import annotations

import logging
import os
import time
from importlib import import_module
from logging.config import fileConfig

from azure.identity import DefaultAzureCredential
from learn_to_cloud_shared.core.azure_auth import AZURE_PG_SCOPE
from learn_to_cloud_shared.core.config import get_settings
from learn_to_cloud_shared.core.database import Base
from sqlalchemy import create_engine

from alembic import context

# Import models so Base.metadata is populated for autogenerate.
import_module("learn_to_cloud_shared.models")

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

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


def _get_sync_database_url() -> str:
    """Return a psycopg2 URL for alembic.

    Sync driver lets alembic run without an asyncio event loop. The
    runtime app uses asyncpg; the two URLs are intentionally separate.
    """
    settings = get_settings()
    if settings.use_azure_postgres:
        token = _get_azure_token_with_retry()
        return (
            f"postgresql+psycopg2://{settings.postgres_user}:{token}"
            f"@{settings.postgres_host}:{settings.postgres_port}/{settings.postgres_database}"
            f"?sslmode=require"
        )

    url = settings.database_url
    if "+asyncpg" in url:
        url = url.replace("+asyncpg", "+psycopg2")
    return url


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode (emit SQL, no DB connection)."""
    context.configure(
        url=_get_sync_database_url(),
        target_metadata=target_metadata,
        literal_binds=True,
        compare_type=True,
        compare_server_default=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations against a live PostgreSQL connection."""
    logger = logging.getLogger("alembic")
    engine = create_engine(_get_sync_database_url())

    try:
        with engine.connect() as connection:
            context.configure(
                connection=connection,
                target_metadata=target_metadata,
                compare_type=True,
                compare_server_default=True,
            )
            with context.begin_transaction():
                context.run_migrations()
    except Exception:
        # Always log so silent failures (e.g. swallowed by some future
        # exception handler) cannot ship green. See issue #432.
        logger.exception("alembic.migration.failed")
        raise
    finally:
        engine.dispose()


def run() -> None:
    if context.is_offline_mode():
        run_migrations_offline()
    else:
        run_migrations_online()


run()
