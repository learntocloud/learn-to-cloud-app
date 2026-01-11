"""Database connection and session management."""

from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase

from .config import get_settings


class Base(DeclarativeBase):
    """Base class for all SQLAlchemy models."""
    pass


settings = get_settings()

# Create async engine - use aiosqlite for SQLite, asyncpg for PostgreSQL
engine = create_async_engine(
    settings.database_url,
    echo=settings.environment == "development",
)

# Session factory
async_session = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


async def get_db() -> AsyncSession:
    """Get a database session."""
    async with async_session() as session:
        return session


async def init_db():
    """Initialize database tables."""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
