from __future__ import annotations

from logging.config import fileConfig

from sqlalchemy import Connection, create_engine, text

# Import models so they register with Base.metadata
import models  # noqa: F401
from alembic import context
from core.config import get_settings
from core.database import Base

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Use SQLAlchemy model metadata for autogenerate
target_metadata = Base.metadata


def _get_sync_database_url() -> str:
    """Get a synchronous database URL for migrations.

    Uses psycopg2 (synchronous driver) instead of asyncpg to avoid
    event loop conflicts when running in background threads.
    """
    settings = get_settings()
    if settings.use_azure_postgres:
        # For Azure with Entra ID auth, we need to get a token
        from azure.identity import DefaultAzureCredential

        credential = DefaultAzureCredential()
        token = credential.get_token(
            "https://ossrdbms-aad.database.windows.net/.default"
        )
        return (
            f"postgresql+psycopg2://{settings.postgres_user}:{token.token}"
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
    import logging

    logger = logging.getLogger("alembic")
    dialect_name = getattr(connection.dialect, "name", "")

    # For PostgreSQL with multiple workers, we need to serialize migrations.
    # We use a session-level advisory lock that blocks until acquired.
    advisory_lock_key = 743028475
    lock_acquired = False
    if dialect_name == "postgresql":
        # Acquire session-level advisory lock (blocks until acquired)
        # Note: pg_advisory_lock is session-level, not transaction-level,
        # so it persists across commits
        result = connection.execute(
            text("SELECT pg_advisory_lock(:key)"), {"key": advisory_lock_key}
        )
        result.close()
        lock_acquired = True
        # Commit the lock acquisition so Alembic starts with a clean transaction
        connection.commit()

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

    # Release the advisory lock for PostgreSQL
    if lock_acquired:
        try:
            result = connection.execute(
                text("SELECT pg_advisory_unlock(:key)"), {"key": advisory_lock_key}
            )
            result.close()
        except Exception as unlock_error:
            # Log but don't raise unlock errors - the lock will be released when
            # the session ends anyway
            logger.warning(f"Failed to release advisory lock: {unlock_error}")

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
