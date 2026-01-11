"""Database connection and session management."""

from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from .config import get_settings


class Base(DeclarativeBase):
    """Base class for all SQLAlchemy models."""
    pass


def _get_engine():
    """Create async engine lazily."""
    settings = get_settings()
    return create_async_engine(
        settings.database_url,
        echo=settings.environment == "development",
    )


# Lazy engine initialization
_engine = None


def get_engine():
    """Get or create the async engine."""
    global _engine
    if _engine is None:
        _engine = _get_engine()
    return _engine


def get_async_session_maker():
    """Get async session factory."""
    return async_sessionmaker(
        get_engine(),
        class_=AsyncSession,
        expire_on_commit=False,
    )


# For backward compatibility
async_session = get_async_session_maker()


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """Get a database session (dependency injection)."""
    async with get_async_session_maker()() as session:
        yield session


async def init_db():
    """Initialize database tables."""
    async with get_engine().begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
