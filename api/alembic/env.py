from __future__ import annotations

import logging
import time
from importlib import import_module
from logging.config import fileConfig

from learn_to_cloud_shared.core.database import Base
from sqlalchemy import Connection, create_engine, text

from alembic import context
from learn_to_cloud._migrations_url import get_sync_database_url

# Import models to register them with Base.metadata
import_module("learn_to_cloud_shared.models")

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata

# Advisory lock key derived from app name hash for uniqueness
_ADVISORY_LOCK_KEY = 743028475  # hash("learn-to-cloud-migrations") % (2**31)

# Lock acquisition timeout (seconds) - prevents indefinite blocking
_LOCK_TIMEOUT_SECONDS = 120


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode."""
    url = get_sync_database_url()
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
            logger.debug("Waiting for migration lock...")
            time.sleep(2)
        else:
            raise RuntimeError(
                f"Failed to acquire migration lock within {_LOCK_TIMEOUT_SECONDS}s. "
                "Another process may be stuck holding the lock."
            )

    migration_error: Exception | None = None
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
        # Always log the underlying error. The previous substring-based
        # "already exists" / "duplicate" swallow turned real UniqueViolations
        # into silent no-ops, masking failed deploys for days. With the
        # session-level advisory lock above, a second worker cannot advance
        # the schema while we hold the lock, so there is no legitimate
        # "another worker already ran it" race to swallow here — any
        # exception is a real failure and must propagate.
        logger.exception("alembic.migration.failed")
        migration_error = e
        try:
            connection.rollback()
        except Exception as rb_err:
            logger.warning("alembic.migration.rollback_failed: %s", rb_err)
    finally:
        if lock_acquired:
            try:
                result = connection.execute(
                    text("SELECT pg_advisory_unlock(:key)"),
                    {"key": _ADVISORY_LOCK_KEY},
                )
                result.close()
                logger.info("Released migration advisory lock")
            except Exception as unlock_error:
                # Session-level advisory locks survive transaction rollback
                # and only disappear on explicit unlock or session close.
                # If unlock fails, invalidate the connection so SQLAlchemy
                # doesn't return it to the pool still holding the lock.
                logger.warning("advisory.lock.release.failed: %s", unlock_error)
                try:
                    connection.invalidate()
                except Exception as inv_err:
                    logger.warning("advisory.lock.invalidate_failed: %s", inv_err)

    if migration_error is not None:
        raise migration_error


def run_migrations_online() -> None:
    """Run migrations using a synchronous PostgreSQL connection.

    Uses psycopg2 (synchronous driver) to avoid event loop conflicts
    when running in a background thread during app startup.
    """
    url = get_sync_database_url()
    engine = create_engine(url)

    with engine.connect() as connection:
        _run_migrations(connection)


def run() -> None:
    if context.is_offline_mode():
        run_migrations_offline()
    else:
        run_migrations_online()


run()
