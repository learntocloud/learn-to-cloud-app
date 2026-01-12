"""Database connection and session management.

Uses SQLAlchemy 2.0 async patterns with proper dependency injection.
Supports lazy initialization for testability.

Supports two authentication modes:
- Local development: SQLite or PostgreSQL with password authentication
- Azure: PostgreSQL with managed identity (passwordless) authentication
"""

import asyncio
import logging
from collections.abc import AsyncGenerator
from typing import Annotated

from fastapi import Depends
from sqlalchemy import event
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase
from sqlalchemy.pool import NullPool
from sqlalchemy import text

from .config import get_settings

logger = logging.getLogger(__name__)

# Cache the Azure credential instance (creating it can be expensive).
_azure_credential = None


class Base(DeclarativeBase):
    """Base class for all SQLAlchemy models."""
    pass


# Module-level state (lazy initialized)
_engine: AsyncEngine | None = None
_async_session_maker: async_sessionmaker[AsyncSession] | None = None


def _get_azure_credential():
    """Get or create the cached DefaultAzureCredential instance."""
    global _azure_credential
    if _azure_credential is None:
        from azure.identity import DefaultAzureCredential

        _azure_credential = DefaultAzureCredential()
    return _azure_credential


def _get_azure_token_sync() -> str:
    """Get an Azure AD token for PostgreSQL authentication (sync, may block)."""
    credential = _get_azure_credential()
    token = credential.get_token("https://ossrdbms-aad.database.windows.net/.default")
    return token.token


async def _get_azure_token() -> str:
    """Get an Azure AD token for PostgreSQL authentication without blocking the event loop."""
    return await asyncio.to_thread(_get_azure_token_sync)


def _build_azure_database_url() -> str:
    """Build a PostgreSQL SQLAlchemy URL for Azure (password provided dynamically)."""
    settings = get_settings()
    return (
        f"postgresql+asyncpg://{settings.postgres_user}"
        f"@{settings.postgres_host}:5432/{settings.postgres_database}"
        f"?ssl=require"
    )


async def _azure_asyncpg_creator():
    """Create an asyncpg connection using a fresh AAD token.

    AAD tokens expire (often ~1 hour). Providing the token dynamically per new
    connection prevents the app from failing once the original token expires.
    """
    settings = get_settings()
    token = await _get_azure_token()

    import asyncpg

    return await asyncpg.connect(
        user=settings.postgres_user,
        password=token,
        host=settings.postgres_host,
        port=5432,
        database=settings.postgres_database,
        ssl="require",
        timeout=30,
    )


def get_engine() -> AsyncEngine:
    """
    Get or create the database engine (lazy initialization).
    
    This allows tests to override settings before the engine is created.
    Uses connection pooling for PostgreSQL to improve performance.
    
    Authentication modes:
    - Azure (POSTGRES_HOST set): Uses managed identity token
    - Local (DATABASE_URL): Uses provided connection string
    """
    global _engine
    if _engine is None:
        settings = get_settings()
        
        # Determine which database URL to use
        if settings.use_azure_postgres:
            # Azure: Use managed identity token (fetched per new connection)
            database_url = _build_azure_database_url()
            is_sqlite = False
            async_creator = _azure_asyncpg_creator
        else:
            # Local: Use DATABASE_URL from environment
            database_url = settings.database_url
            is_sqlite = "sqlite" in database_url
            async_creator = None
        
        _engine = create_async_engine(
            database_url,
            echo=settings.environment == "development",
            # SQLite doesn't support connection pooling
            poolclass=NullPool if is_sqlite else None,
            # Connection pool settings for PostgreSQL (asyncpg)
            **({} if is_sqlite else {
                "pool_size": 10,          # Base connections to keep open
                "max_overflow": 20,       # Extra connections when busy
                "pool_timeout": 30,       # Wait time for available connection
                "pool_recycle": 300,      # Recycle connections every 5 min (tokens expire)
                "pool_pre_ping": True,    # Verify connections before use
            }),
            **({} if async_creator is None else {"async_creator": async_creator}),
        )

        # SQLite does not enforce foreign keys unless explicitly enabled.
        # We rely on ON DELETE CASCADE for user deletion.
        if is_sqlite:
            @event.listens_for(_engine.sync_engine, "connect")
            def _set_sqlite_pragma(dbapi_connection, connection_record) -> None:  # type: ignore[no-redef]
                cursor = dbapi_connection.cursor()
                cursor.execute("PRAGMA foreign_keys=ON")
                cursor.close()
        
        # Instrument SQLAlchemy for query performance tracking
        try:
            from .telemetry import instrument_sqlalchemy_engine
            instrument_sqlalchemy_engine(_engine)
        except Exception as e:
            logger.warning(f"Failed to instrument SQLAlchemy for telemetry: {e}")
            
    return _engine


def get_session_maker() -> async_sessionmaker[AsyncSession]:
    """Get or create the session factory (lazy initialization)."""
    global _async_session_maker
    if _async_session_maker is None:
        _async_session_maker = async_sessionmaker(
            bind=get_engine(),
            class_=AsyncSession,
            expire_on_commit=False,
            autocommit=False,
            autoflush=False,
        )
    return _async_session_maker


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """
    FastAPI dependency that provides a database session.
    
    Usage:
        @app.get("/items")
        async def get_items(db: DbSession):
            result = await db.execute(select(Item))
            return result.scalars().all()
    """
    session_maker = get_session_maker()
    async with session_maker() as session:
        try:
            yield session
            if session.new or session.dirty or session.deleted:
                await session.commit()
            elif session.in_transaction():
                # End any implicit read-only transaction cleanly.
                await session.rollback()
        except Exception:
            await session.rollback()
            raise


# Type alias for cleaner dependency injection
DbSession = Annotated[AsyncSession, Depends(get_db)]


async def init_db() -> None:
    """Initialize database tables (create all)."""
    settings = get_settings()
    engine = get_engine()
    async with engine.begin() as conn:
        if settings.reset_db_on_startup:
            if settings.environment != "development":
                logger.warning(
                    "reset_db_on_startup is enabled but environment is not development; skipping drop_all"
                )
            else:
                await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)


async def check_db_connection() -> None:
    """Verify the database is reachable.

    Raises:
        Exception if the database can't be reached.
    """
    engine = get_engine()
    async with engine.connect() as conn:
        await conn.execute(text("SELECT 1"))


async def cleanup_old_webhooks(days: int = 7) -> int:
    """
    Remove ProcessedWebhook entries older than the specified days.
    
    This prevents the table from growing indefinitely. Webhooks older
    than 7 days are unlikely to be replayed, so they can be safely removed.
    
    Args:
        days: Number of days to retain webhooks (default: 7)
        
    Returns:
        Number of deleted entries
    """
    from datetime import datetime, timezone, timedelta
    from sqlalchemy import delete
    from .models import ProcessedWebhook
    
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    session_maker = get_session_maker()
    
    async with session_maker() as session:
        result = await session.execute(
            delete(ProcessedWebhook).where(ProcessedWebhook.processed_at < cutoff)
        )
        await session.commit()
        return result.rowcount or 0


def reset_db_state() -> None:
    """
    Reset database state for testing.

    Call this in test fixtures to ensure a fresh database connection
    after changing settings.

    Example:
        @pytest.fixture
        def test_settings(monkeypatch):
            get_settings.cache_clear()
            monkeypatch.setenv("DATABASE_URL", "sqlite+aiosqlite:///:memory:")
            reset_db_state()
            yield
    """
    global _engine, _async_session_maker
    _engine = None
    _async_session_maker = None


async def upsert_on_conflict(
    db: AsyncSession,
    model: type,
    values: dict,
    index_elements: list[str],
    update_fields: list[str],
) -> None:
    """
    Perform a dialect-aware upsert (INSERT ... ON CONFLICT DO UPDATE).

    Supports PostgreSQL and SQLite. Falls back to select-then-update for
    other dialects.

    Args:
        db: The async database session
        model: The SQLAlchemy model class
        values: Dict of column name -> value for the insert
        index_elements: Column names that form the unique constraint
        update_fields: Column names to update on conflict
    """
    bind = db.get_bind()
    dialect_name = bind.dialect.name if bind is not None else ""

    update_set = {field: values[field] for field in update_fields if field in values}

    if dialect_name == "postgresql":
        from sqlalchemy.dialects.postgresql import insert as pg_insert

        stmt = pg_insert(model).values(**values)
        stmt = stmt.on_conflict_do_update(
            index_elements=index_elements,
            set_=update_set,
        )
        await db.execute(stmt)

    elif dialect_name == "sqlite":
        from sqlalchemy.dialects.sqlite import insert as sqlite_insert

        stmt = sqlite_insert(model).values(**values)
        stmt = stmt.on_conflict_do_update(
            index_elements=index_elements,
            set_=update_set,
        )
        await db.execute(stmt)

    else:
        # Fallback for other dialects: select then insert/update
        from sqlalchemy import select, and_

        conditions = [getattr(model, elem) == values[elem] for elem in index_elements]
        result = await db.execute(select(model).where(and_(*conditions)))
        existing = result.scalar_one_or_none()

        if existing:
            for field in update_fields:
                if field in values:
                    setattr(existing, field, values[field])
        else:
            db.add(model(**values))
