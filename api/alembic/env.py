from __future__ import annotations

import asyncio
from logging.config import fileConfig

from sqlalchemy import Connection, text

# Import models so they register with Base.metadata
import models  # noqa: F401
from alembic import context
from core.config import get_settings
from core.database import Base, get_engine

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Use SQLAlchemy model metadata for autogenerate
target_metadata = Base.metadata


def _get_database_url() -> str:
    """Resolve the database URL to use for migrations."""
    settings = get_settings()
    if settings.use_azure_postgres:
        # Match core.database._build_azure_database_url() (token provided dynamically).
        return (
            f"postgresql+asyncpg://{settings.postgres_user}"
            f"@{settings.postgres_host}:5432/{settings.postgres_database}"
            f"?ssl=require"
        )

    return settings.database_url


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode."""
    url = _get_database_url()
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
    dialect_name = getattr(connection.dialect, "name", "")

    # For PostgreSQL with multiple workers, we need to serialize migrations.
    # We use a session-level advisory lock that blocks until acquired.
    advisory_lock_key = 743028475
    if dialect_name == "postgresql":
        # Acquire session-level advisory lock (blocks until acquired)
        result = connection.execute(
            text("SELECT pg_advisory_lock(:key)"), {"key": advisory_lock_key}
        )
        result.close()

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
        # Check if this is a "table already exists" error - another worker may have
        # already run migrations even though we had the lock (race at startup)
        error_str = str(e).lower()
        if "already exists" in error_str or "duplicate" in error_str:
            # Migrations were already applied by another process, this is OK
            import logging

            logging.getLogger("alembic").info(
                "Migrations already applied by another process, continuing..."
            )
        else:
            raise
    finally:
        # Release the advisory lock for PostgreSQL
        if dialect_name == "postgresql":
            result = connection.execute(
                text("SELECT pg_advisory_unlock(:key)"), {"key": advisory_lock_key}
            )
            result.close()


async def run_migrations_online() -> None:
    """Run migrations in 'online' mode using the app's async engine."""
    connectable = get_engine()

    async with connectable.connect() as connection:
        await connection.run_sync(_run_migrations)


def run() -> None:
    if context.is_offline_mode():
        run_migrations_offline()
    else:
        asyncio.run(run_migrations_online())


run()
