"""Database engine, session, and pool management.

Authentication modes:
- Local: password auth (Docker)
- Azure: managed identity via core.azure_auth
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import AsyncGenerator
from typing import Annotated

import asyncpg
from fastapi import Depends, Request
from sqlalchemy import text
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase

from learn_to_cloud_shared.core.azure_auth import get_token as _get_azure_token
from learn_to_cloud_shared.core.config import DatabaseConfig
from learn_to_cloud_shared.core.observability import instrument_database

logger = logging.getLogger(__name__)


class Base(DeclarativeBase):
    pass


def _build_azure_database_url(settings: DatabaseConfig) -> str:
    return (
        f"postgresql+asyncpg://{settings.user}"
        f"@{settings.host}:{settings.port}/{settings.name}"
        f"?ssl=require"
    )


async def _azure_asyncpg_creator(settings: DatabaseConfig):
    """Create an asyncpg connection using a fresh Entra ID token.

    Tokens expire (~1 hour), so each new connection fetches a fresh one
    via managed identity.
    """
    token = await _get_azure_token()

    try:
        return await asyncpg.connect(
            user=settings.user,
            password=token,
            host=settings.host,
            port=settings.port,
            database=settings.name,
            ssl="require",
            timeout=settings.timeout,
            server_settings={
                "statement_timeout": str(settings.statement_timeout_ms),
            },
        )
    except asyncpg.PostgresConnectionError:
        logger.exception(
            "db.connection.failed",
            extra={"host": settings.host, "port": settings.port},
        )
        raise


def create_engine(settings: DatabaseConfig) -> AsyncEngine:
    if settings.use_azure_postgres:
        database_url = _build_azure_database_url(settings)

        async def async_creator() -> asyncpg.Connection:
            return await _azure_asyncpg_creator(settings)

    else:
        database_url = settings.url
        async_creator = None

    # Note: pool_pre_ping is intentionally NOT enabled. It interacts badly
    # with the asyncpg dialect's transaction state tracking and required a
    # brittle private-state workaround. pool_recycle keeps connections fresh
    # within Azure's idle timeout window; the (rare) silently-dropped
    # connection surfaces as a single failed request that the user retries.
    engine_kwargs: dict = {
        "echo": settings.echo,
        "pool_size": settings.pool_size,
        "max_overflow": settings.pool_max_overflow,
        "pool_timeout": settings.pool_timeout,
        "pool_recycle": settings.pool_recycle,
    }

    if async_creator is None:
        engine_kwargs["connect_args"] = {
            "server_settings": {"statement_timeout": str(settings.statement_timeout_ms)}
        }
    else:
        engine_kwargs["async_creator"] = async_creator

    engine = create_async_engine(database_url, **engine_kwargs)

    instrument_database(engine)

    return engine


def create_session_maker(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(
        bind=engine,
        class_=AsyncSession,
        expire_on_commit=False,
        autocommit=False,
        autoflush=False,
    )


async def get_db(request: Request) -> AsyncGenerator[AsyncSession]:
    """Auto-commits on success, rolls back on exception.

    Notes:
        - Use flush() if you need auto-generated IDs mid-request
        - Do NOT call commit() - this dependency handles it
    """
    session_maker: async_sessionmaker[AsyncSession] = request.app.state.session_maker
    async with session_maker() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            try:
                await session.rollback()
            except Exception as rollback_err:
                logger.warning("db.rollback.failed", extra={"error": str(rollback_err)})
            raise


async def get_db_readonly(request: Request) -> AsyncGenerator[AsyncSession]:
    """Read-only session — PostgreSQL rejects any write attempts.

    Uses SET TRANSACTION READ ONLY so INSERT/UPDATE/DELETE raise
    an immediate error instead of silently rolling back on close.
    """
    session_maker: async_sessionmaker[AsyncSession] = request.app.state.session_maker
    async with session_maker() as session:
        try:
            await session.execute(text("SET TRANSACTION READ ONLY"))
            yield session
        except Exception:
            try:
                await session.rollback()
            except Exception as rollback_err:
                logger.warning("db.rollback.failed", extra={"error": str(rollback_err)})
            raise


DbSession = Annotated[AsyncSession, Depends(get_db)]
DbSessionReadOnly = Annotated[AsyncSession, Depends(get_db_readonly)]


async def init_db(engine: AsyncEngine, settings: DatabaseConfig) -> None:
    """Verify database is reachable. Schema managed via migrations."""
    logger.info("db.connectivity.verifying")

    async with asyncio.timeout(settings.timeout):
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
            await conn.rollback()
    logger.info("db.connectivity.verified")


async def dispose_engine(engine: AsyncEngine) -> None:
    await engine.dispose()
    logger.info("db.engine.disposed")


async def check_db_connection(engine: AsyncEngine, settings: DatabaseConfig) -> None:
    """Verify database is reachable."""
    async with asyncio.timeout(settings.timeout):
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
            await conn.rollback()
