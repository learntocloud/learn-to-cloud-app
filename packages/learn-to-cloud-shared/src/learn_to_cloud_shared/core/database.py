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
from sqlalchemy import event, text
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase

from learn_to_cloud_shared.core.azure_auth import get_token as _get_azure_token
from learn_to_cloud_shared.core.config import get_settings
from learn_to_cloud_shared.core.observability import instrument_database

logger = logging.getLogger(__name__)


class Base(DeclarativeBase):
    pass


def _build_azure_database_url() -> str:
    settings = get_settings()
    return (
        f"postgresql+asyncpg://{settings.postgres_user}"
        f"@{settings.postgres_host}:{settings.postgres_port}/{settings.postgres_database}"
        f"?ssl=require"
    )


async def _azure_asyncpg_creator():
    """Create an asyncpg connection using a fresh Entra ID token.

    Tokens expire (~1 hour), so each new connection fetches a fresh one
    via managed identity.
    """
    settings = get_settings()
    token = await _get_azure_token()

    try:
        return await asyncpg.connect(
            user=settings.postgres_user,
            password=token,
            host=settings.postgres_host,
            port=settings.postgres_port,
            database=settings.postgres_database,
            ssl="require",
            timeout=settings.db_timeout,
            server_settings={
                "statement_timeout": str(settings.db_statement_timeout_ms),
            },
        )
    except asyncpg.PostgresConnectionError:
        logger.exception(
            "db.connection.failed",
            extra={"host": settings.postgres_host, "port": settings.postgres_port},
        )
        raise


def _setup_pool_event_listeners(engine: AsyncEngine) -> None:
    pool = engine.sync_engine.pool

    @event.listens_for(pool, "checkout")
    def _on_checkout(dbapi_conn, connection_record, connection_proxy):
        # Clean up lingering transaction state that causes asyncpg's
        # "cannot use Connection.transaction() in a manually started
        # transaction" error on next use.
        raw_conn = dbapi_conn._connection
        if raw_conn.is_in_transaction():
            dbapi_conn.await_(raw_conn.execute("ROLLBACK"))
            # Reset private asyncpg adapter state (verified 2.0.46).
            try:
                dbapi_conn._transaction = None
                dbapi_conn._started = False
            except AttributeError:
                pass


def create_engine() -> AsyncEngine:
    settings = get_settings()

    if settings.use_azure_postgres:
        database_url = _build_azure_database_url()
        async_creator = _azure_asyncpg_creator
    else:
        database_url = settings.database_url
        async_creator = None

    engine_kwargs: dict = {
        "echo": settings.db_echo,
        "pool_size": settings.db_pool_size,
        "max_overflow": settings.db_pool_max_overflow,
        "pool_timeout": settings.db_pool_timeout,
        "pool_recycle": settings.db_pool_recycle,
        "pool_pre_ping": True,
    }

    if async_creator is None:
        engine_kwargs["connect_args"] = {
            "server_settings": {
                "statement_timeout": str(settings.db_statement_timeout_ms)
            }
        }
    else:
        engine_kwargs["async_creator"] = async_creator

    engine = create_async_engine(database_url, **engine_kwargs)

    _setup_pool_event_listeners(engine)
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


async def init_db(engine: AsyncEngine) -> None:
    """Verify database is reachable. Schema managed via migrations."""
    logger.info("db.connectivity.verifying")

    async with asyncio.timeout(get_settings().db_timeout):
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
            await conn.rollback()
    logger.info("db.connectivity.verified")


async def dispose_engine(engine: AsyncEngine) -> None:
    await engine.dispose()
    logger.info("db.engine.disposed")


async def check_db_connection(engine: AsyncEngine) -> None:
    """Verify database is reachable."""
    async with asyncio.timeout(get_settings().db_timeout):
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
            await conn.rollback()
