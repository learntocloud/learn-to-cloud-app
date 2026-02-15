"""Database engine, session, and pool management.

Authentication modes:
- Local: password auth (Docker)
- Azure: managed identity via core.azure_auth
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import AsyncGenerator
from typing import Annotated, NamedTuple, TypedDict

from fastapi import Depends, Request
from sqlalchemy import event, text
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase
from sqlalchemy.pool import QueuePool

from core.azure_auth import get_token as _get_azure_token
from core.azure_auth import reset_credential as _reset_azure_credential
from core.config import get_settings

logger = logging.getLogger(__name__)


class Base(DeclarativeBase):
    pass


class PoolStatus(NamedTuple):
    """Connection pool status for health checks."""

    pool_size: int
    checked_out: int
    overflow: int
    checked_in: int


class HealthCheckResult(TypedDict):
    """Return type for comprehensive_health_check."""

    database: bool
    azure_auth: bool | None
    pool: PoolStatus | None


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

    import asyncpg

    try:
        return await asyncpg.connect(
            user=settings.postgres_user,
            password=token,
            host=settings.postgres_host,
            port=settings.postgres_port,
            database=settings.postgres_database,
            ssl="require",
            timeout=30,
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

        if isinstance(pool, QueuePool):
            checked_out = pool.checkedout()
            overflow = pool.overflow()
            pool_size = pool.size()
            if overflow > 0:
                logger.warning(
                    "db.pool.overflow",
                    extra={
                        "db_pool_checked_out": checked_out,
                        "db_pool_size": pool_size,
                        "db_pool_overflow_count": overflow,
                    },
                )


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
        # pool_pre_ping is disabled because SQLAlchemy's asyncpg adapter uses
        # Connection.transaction() for the ping, which can conflict with
        # asyncpg's strict protocol-level transaction state tracking.
        # pool_recycle provides staleness protection instead.
        "pool_pre_ping": False,
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

    try:
        from .observability import instrument_sqlalchemy_engine

        instrument_sqlalchemy_engine(engine)
    except Exception:
        logger.warning("database.observability_setup.failed", exc_info=True)

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

    async with asyncio.timeout(30):
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
            await conn.rollback()
    logger.info("db.connectivity.verified")


async def warm_pool(engine: AsyncEngine) -> None:
    """Pre-fill the connection pool so early requests don't pay connection cost."""
    settings = get_settings()
    warm_count = min(settings.db_pool_size - 1, 3)  # already have 1 from init_db
    if warm_count <= 0:
        return

    logger.info("db.pool.warming", extra={"extra_connections": warm_count})
    try:
        async with asyncio.timeout(30):

            async def _warm_one() -> None:
                async with engine.connect() as conn:
                    await conn.execute(text("SELECT 1"))
                    await conn.rollback()

            await asyncio.gather(
                *[_warm_one() for _ in range(warm_count)],
                return_exceptions=True,
            )
        logger.info("db.pool.warmed")
    except Exception as e:
        # Non-fatal — the pool will create connections on demand
        logger.warning("db.pool.warming.failed", extra={"error": str(e)})


async def dispose_engine(engine: AsyncEngine) -> None:
    await engine.dispose()
    logger.info("db.engine.disposed")


async def check_db_connection(engine: AsyncEngine) -> None:
    """Verify database is reachable (30s timeout)."""
    async with asyncio.timeout(30):
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
            await conn.rollback()


def get_pool_status(engine: AsyncEngine) -> PoolStatus | None:
    """Returns pool status, or None if pool is not a QueuePool."""
    pool = engine.sync_engine.pool

    if isinstance(pool, QueuePool):
        return PoolStatus(
            pool_size=pool.size(),
            checked_out=pool.checkedout(),
            overflow=pool.overflow(),
            checked_in=pool.checkedin(),
        )
    return None


async def check_azure_token_acquisition() -> bool:
    """Verify managed identity can acquire tokens (separate from DB connectivity)."""
    settings = get_settings()
    if not settings.use_azure_postgres:
        return True

    await _get_azure_token()
    return True


async def comprehensive_health_check(engine: AsyncEngine) -> HealthCheckResult:
    """Run database connectivity, Azure auth, and pool status checks."""
    settings = get_settings()
    result: HealthCheckResult = {
        "database": False,
        "azure_auth": None,
        "pool": None,
    }

    if settings.use_azure_postgres:
        try:
            await check_azure_token_acquisition()
            result["azure_auth"] = True
        except Exception:
            result["azure_auth"] = False
            # Don't proceed to DB check if auth is broken
            return result

    try:
        await check_db_connection(engine)
        result["database"] = True
    except Exception:
        result["database"] = False

    result["pool"] = get_pool_status(engine)

    return result


async def reset_azure_credential() -> None:
    """For testing — resets cached credential (lock-protected)."""
    await _reset_azure_credential()
