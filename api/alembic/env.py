from __future__ import annotations

import logging
import sys
import time
from logging.config import fileConfig
from pathlib import Path

from sqlalchemy import Connection, create_engine, text

# Ensure parent directory (api/) is in Python path for module imports
sys.path.insert(0, str(Path(__file__).parent.parent))

# Import models so they register with Base.metadata
import models  # noqa: F401
from alembic import context
from core.config import get_settings
from core.database import (
    _AZURE_PG_SCOPE,
    _AZURE_RETRY_ATTEMPTS,
    _AZURE_RETRY_MIN_WAIT,
    Base,
)

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Use SQLAlchemy model metadata for autogenerate
target_metadata = Base.metadata

# Advisory lock key derived from app name hash for uniqueness
_ADVISORY_LOCK_KEY = 743028475  # hash("learn-to-cloud-migrations") % (2**31)

# Lock acquisition timeout (seconds) - prevents indefinite blocking
_LOCK_TIMEOUT_SECONDS = 120


def _get_azure_token_with_retry() -> str:
    """Get Azure AD token with retry logic for transient failures.

    Uses sync credential since Alembic runs outside asyncio event loop.
    Reuses retry constants from database module for consistency.
    """
    from azure.identity import DefaultAzureCredential

    last_error = None
    for attempt in range(_AZURE_RETRY_ATTEMPTS):
        try:
            credential = DefaultAzureCredential()
            token = credential.get_token(_AZURE_PG_SCOPE)
            return token.token
        except Exception as e:
            last_error = e
            if attempt < _AZURE_RETRY_ATTEMPTS - 1:
                delay = _AZURE_RETRY_MIN_WAIT * (2**attempt)  # Exponential backoff
                time.sleep(delay)

    raise RuntimeError(
        f"Failed to acquire Azure AD token after {_AZURE_RETRY_ATTEMPTS} attempts"
    ) from last_error


def _get_sync_database_url() -> str:
    """Get a synchronous database URL for migrations.

    Uses psycopg2 (synchronous driver) instead of asyncpg to avoid
    event loop conflicts when running in background threads.
    """
    settings = get_settings()
    if settings.use_azure_postgres:
        # For Azure with Entra ID auth, we need to get a token with retry
        token = _get_azure_token_with_retry()
        return (
            f"postgresql+psycopg2://{settings.postgres_user}:{token}"
            f"@{settings.postgres_host}:5432/{settings.postgres_database}"
            f"?sslmode=require"
        )

    # Convert asyncpg URL to psycopg2 URL for local dev
    url = settings.database_url
    if "+asyncpg" in url:
        url = url.replace("+asyncpg", "+psycopg2")
    return url


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode."""
    url = _get_sync_database_url()
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        compare_type=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def _run_migrations(connection: Connection) -> None:
    logger = logging.getLogger("alembic")
    dialect_name = getattr(connection.dialect, "name", "")

    # For PostgreSQL with multiple workers, we need to serialize migrations.
    # We use a session-level advisory lock with a timeout to prevent deadlocks.
    lock_acquired = False
    if dialect_name == "postgresql":
        # Try to acquire lock with timeout (prevents indefinite blocking)
        # pg_try_advisory_lock returns immediately, we poll with timeout
        start_time = time.time()
        while time.time() - start_time < _LOCK_TIMEOUT_SECONDS:
            result = connection.execute(
                text("SELECT pg_try_advisory_lock(:key)"),
                {"key": _ADVISORY_LOCK_KEY},
            )
            acquired = result.scalar()
            result.close()
            if acquired:
                lock_acquired = True
                # Commit the lock acquisition so Alembic starts clean
                connection.commit()
                logger.info("Acquired migration advisory lock")
                break
            # Another process has the lock, wait and retry
            logger.debug("Waiting for migration lock...")
            time.sleep(2)
        else:
            raise RuntimeError(
                f"Failed to acquire migration lock within {_LOCK_TIMEOUT_SECONDS}s. "
                "Another process may be stuck holding the lock."
            )

    migration_error = None
    try:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=True,
            render_as_batch=True,
        )

        with context.begin_transaction():
            context.run_migrations()
    except Exception as e:
        migration_error = e
        # Check if this is a "table already exists" error - another worker may have
        # already run migrations even though we had the lock (race at startup)
        error_str = str(e).lower()
        if "already exists" in error_str or "duplicate" in error_str:
            # Migrations were already applied by another process, this is OK
            logger.info("Migrations already applied by another process, continuing...")
            migration_error = None  # Don't re-raise this error
        else:
            # For other errors, rollback the failed transaction
            try:
                connection.rollback()
            except Exception:
                pass  # Ignore rollback errors
    finally:
        # Always release the advisory lock for PostgreSQL
        if lock_acquired:
            try:
                result = connection.execute(
                    text("SELECT pg_advisory_unlock(:key)"),
                    {"key": _ADVISORY_LOCK_KEY},
                )
                result.close()
                logger.info("Released migration advisory lock")
            except Exception as unlock_error:
                # Log but don't raise - lock released when session ends anyway
                logger.warning("advisory.lock.release.failed: %s", unlock_error)

    # Re-raise the migration error if it wasn't a "table already exists" error
    if migration_error is not None:
        raise migration_error


def run_migrations_online() -> None:
    """Run migrations using a synchronous PostgreSQL connection.

    Uses psycopg2 (synchronous driver) to avoid event loop conflicts
    when running in a background thread during app startup.
    """
    url = _get_sync_database_url()
    engine = create_engine(url)

    with engine.connect() as connection:
        _run_migrations(connection)


def run() -> None:
    if context.is_offline_mode():
        run_migrations_offline()
    else:
        # run_migrations_online is now synchronous (uses psycopg2)
        run_migrations_online()


run()
