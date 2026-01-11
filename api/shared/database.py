"""Database connection and session management.

Uses SQLAlchemy 2.0 async patterns with proper dependency injection.
Supports lazy initialization for testability.

Supports two authentication modes:
- Local development: SQLite or PostgreSQL with password authentication
- Azure: PostgreSQL with managed identity (passwordless) authentication
"""

from collections.abc import AsyncGenerator
from typing import Annotated

from fastapi import Depends
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase
from sqlalchemy.pool import NullPool

from .config import get_settings


class Base(DeclarativeBase):
    """Base class for all SQLAlchemy models."""
    pass


# Module-level state (lazy initialized)
_engine: AsyncEngine | None = None
_async_session_maker: async_sessionmaker[AsyncSession] | None = None


def _get_azure_token() -> str:
    """
    Get an Azure AD token for PostgreSQL authentication.
    
    Uses DefaultAzureCredential which automatically works with:
    - Managed Identity (in Azure Container Apps)
    - Azure CLI credentials (for local development with `az login`)
    - Environment variables (AZURE_CLIENT_ID, etc.)
    """
    from azure.identity import DefaultAzureCredential
    
    credential = DefaultAzureCredential()
    # PostgreSQL requires this specific scope for Azure AD authentication
    token = credential.get_token("https://ossrdbms-aad.database.windows.net/.default")
    return token.token


def _build_azure_database_url() -> str:
    """
    Build the PostgreSQL connection URL using managed identity.
    
    The token is used as the password in the connection string.
    """
    settings = get_settings()
    token = _get_azure_token()
    
    # URL encode the token as it may contain special characters
    from urllib.parse import quote_plus
    encoded_token = quote_plus(token)
    
    return (
        f"postgresql+asyncpg://{settings.postgres_user}:{encoded_token}"
        f"@{settings.postgres_host}:5432/{settings.postgres_database}"
        f"?ssl=require"
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
            # Azure: Build URL with managed identity token
            database_url = _build_azure_database_url()
            is_sqlite = False
        else:
            # Local: Use DATABASE_URL from environment
            database_url = settings.database_url
            is_sqlite = "sqlite" in database_url
        
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
        )
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
            await session.commit()
        except Exception:
            await session.rollback()
            raise


# Type alias for cleaner dependency injection
DbSession = Annotated[AsyncSession, Depends(get_db)]


async def init_db() -> None:
    """Initialize database tables (create all)."""
    engine = get_engine()
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


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
