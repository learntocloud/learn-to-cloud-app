"""Database engine, session, and pool management.

Authentication modes:
- Local: password auth (Docker)
- Azure: managed identity via core.azure_auth
"""

from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import AsyncGenerator
from typing import Annotated, Any

import asyncpg
from fastapi import Depends, Request
from sqlalchemy import event, text
from sqlalchemy.engine import Connection, ExceptionContext
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
from learn_to_cloud_shared.core.outbound import (
    DEPENDENCY_NAME,
    OTHER,
    Dependency,
    classify,
    outbound_call,
    record_attempt,
)

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
        async with outbound_call(
            Dependency.POSTGRES,
            "connect",
            span_name="connect",
            span_attributes={
                "db.system.name": "postgresql",
                "server.address": settings.host,
                "server.port": settings.port,
            },
        ):
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
    except Exception as exc:
        logger.error(
            "db.connection.failed",
            extra={
                "error.type": classify(exc),
                DEPENDENCY_NAME: Dependency.POSTGRES.value,
            },
        )
        raise


_SQL_OPERATIONS = frozenset(
    {"SELECT", "INSERT", "UPDATE", "DELETE", "WITH", "BEGIN", "COMMIT", "ROLLBACK"}
)
_STATEMENT_STARTS = "learn_to_cloud.statement_starts"


def _sql_operation(statement: str | None) -> str:
    words = (statement or "").split(maxsplit=1)
    verb = words[0].upper() if words else ""
    return verb if verb in _SQL_OPERATIONS else OTHER


def measure_statements(engine: AsyncEngine) -> None:
    """Record every statement as a ``postgres`` dependency attempt."""
    sync_engine = engine.sync_engine

    @event.listens_for(sync_engine, "before_cursor_execute", named=True)
    def _started(conn: Connection, **_: Any) -> None:
        conn.info.setdefault(_STATEMENT_STARTS, []).append(time.perf_counter())

    @event.listens_for(sync_engine, "after_cursor_execute", named=True)
    def _finished(conn: Connection, statement: str, **_: Any) -> None:
        starts = conn.info.get(_STATEMENT_STARTS)
        if starts:
            record_attempt(
                Dependency.POSTGRES,
                _sql_operation(statement),
                time.perf_counter() - starts.pop(),
            )

    @event.listens_for(sync_engine, "handle_error")
    def _failed(context: ExceptionContext) -> None:
        conn = context.connection
        starts = conn.info.get(_STATEMENT_STARTS) if conn is not None else None
        if starts:
            record_attempt(
                Dependency.POSTGRES,
                _sql_operation(context.statement),
                time.perf_counter() - starts.pop(),
                error_type=classify(context.original_exception),
            )


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
        "hide_parameters": True,
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
    measure_statements(engine)
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
                logger.warning(
                    "db.rollback.failed",
                    extra={"error.type": type(rollback_err).__name__},
                )
            raise


DbSession = Annotated[AsyncSession, Depends(get_db)]


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
