"""Database engine, session, and pool management.

Authentication modes:
- Local: password auth (Docker)
- Azure: managed identity via core.azure_auth
"""

from __future__ import annotations

import asyncio
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
from core.logger import get_logger
from core.wide_event import set_wide_event_fields

logger = get_logger(__name__)


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


# =============================================================================
# Engine Creation (called once at startup)
# =============================================================================


def _build_azure_database_url() -> str:
    settings = get_settings()
    return (
        f"postgresql+asyncpg://{settings.postgres_user}"
        f"@{settings.postgres_host}:{settings.postgres_port}/{settings.postgres_database}"
        f"?ssl=require"
    )


async def _azure_asyncpg_creator():
    """Create an asyncpg connection using a fresh AAD token.

    AAD tokens expire (often ~1 hour). Providing the token dynamically per new
    connection prevents the app from failing once the original token expires.

    Note: connect_args from create_async_engine is bypassed when using async_creator,
    so we must set server_settings (like statement_timeout) directly here.

    Raises:
        TimeoutError: If token acquisition or connection takes too long.
        asyncpg.PostgresError: If connection fails after token is obtained.
    """
    settings = get_settings()

    # Token acquisition has its own retry/timeout logic
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
            # Apply statement_timeout here since connect_args is bypassed
            # with async_creator
            server_settings={
                "statement_timeout": str(settings.db_statement_timeout_ms),
            },
        )
    except asyncpg.PostgresConnectionError as e:
        # Log connection errors with host (but not credentials)
        set_wide_event_fields(
            db_error="connection_failed",
            db_host=settings.postgres_host,
            db_error_detail=str(e),
        )
        raise


def _setup_pool_event_listeners(engine: AsyncEngine) -> None:
    # Note: AsyncAdaptedQueuePool is a subclass of QueuePool
    pool = engine.sync_engine.pool

    @event.listens_for(pool, "checkout")
    def _on_checkout(dbapi_conn, connection_record, connection_proxy):
        # asyncpg tracks protocol-level transaction state independently from
        # the SQLAlchemy adapter.  If a connection is returned to the pool
        # with lingering state (e.g. after an interrupted request), the next
        # checkout raises "cannot use Connection.transaction() in a manually
        # started transaction".
        raw_conn = dbapi_conn._connection
        if raw_conn.is_in_transaction():
            dbapi_conn.await_(raw_conn.execute("ROLLBACK"))
            # Private attrs of SQLAlchemy's asyncpg AdaptedConnection
            # (verified against 2.0.46). try/except so a future upgrade
            # surfaces a warning instead of crashing.
            try:
                dbapi_conn._transaction = None
                dbapi_conn._started = False
            except AttributeError:
                set_wide_event_fields(
                    db_error="checkout_reset_failed",
                    db_error_detail=(
                        "asyncpg adapter internals changed — "
                        "_transaction/_started attributes missing"
                    ),
                )

        if isinstance(pool, QueuePool):
            checked_out = pool.checkedout()
            overflow = pool.overflow()
            pool_size = pool.size()
            if overflow > 0:
                set_wide_event_fields(
                    db_pool_overflow=True,
                    db_pool_checked_out=checked_out,
                    db_pool_size=pool_size,
                    db_pool_overflow_count=overflow,
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

    # connect_args only applies when NOT using async_creator
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
        from .telemetry import instrument_sqlalchemy_engine

        instrument_sqlalchemy_engine(engine)
    except Exception as e:
        set_wide_event_fields(
            db_error="telemetry_instrumentation_failed",
            db_error_detail=str(e),
        )

    return engine


def create_session_maker(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(
        bind=engine,
        class_=AsyncSession,
        expire_on_commit=False,
        autocommit=False,
        autoflush=False,
    )


# =============================================================================
# FastAPI Dependencies (access state via Request)
# =============================================================================


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
                logger.warning("db.rollback.failed", error=str(rollback_err))
            raise


async def get_db_readonly(request: Request) -> AsyncGenerator[AsyncSession]:
    """Session for read-only operations (no commit)."""
    session_maker: async_sessionmaker[AsyncSession] = request.app.state.session_maker
    async with session_maker() as session:
        try:
            yield session
        except Exception:
            try:
                await session.rollback()
            except Exception as rollback_err:
                logger.warning("db.rollback.failed", error=str(rollback_err))
            raise


DbSession = Annotated[AsyncSession, Depends(get_db)]
DbSessionReadOnly = Annotated[AsyncSession, Depends(get_db_readonly)]


# =============================================================================
# Lifecycle Functions (called from lifespan)
# =============================================================================


async def init_db(engine: AsyncEngine) -> None:
    """Verify database is reachable. Schema managed via migrations."""
    logger.info("db.connectivity.verifying")

    try:
        async with asyncio.timeout(30):
            async with engine.connect() as conn:
                await conn.execute(text("SELECT 1"))
                # Explicit rollback so asyncpg 0.30.0 doesn't leave the
                # connection in a "manually started transaction" state when
                # it's returned to the pool.
                await conn.rollback()
        logger.info("db.connectivity.verified")
    except TimeoutError:
        set_wide_event_fields(db_error="connection_timeout", db_timeout_seconds=30)
        raise
    except Exception as e:
        set_wide_event_fields(db_error="connection_failed", db_error_detail=str(e))
        raise


async def warm_pool(engine: AsyncEngine) -> None:
    """Pre-fill the connection pool in the background.

    Called as a fire-and-forget task *after* the app starts serving so
    startup latency isn't affected.  The first few requests may still
    create connections on demand, but subsequent ones will hit warm slots.
    """
    settings = get_settings()
    warm_count = min(settings.db_pool_size - 1, 3)  # already have 1 from init_db
    if warm_count <= 0:
        return

    logger.info("db.pool.warming", extra_connections=warm_count)
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
        logger.warning("db.pool.warming.failed", error=str(e))


async def dispose_engine(engine: AsyncEngine) -> None:
    await engine.dispose()
    logger.info("db.engine.disposed")


# =============================================================================
# Health Check Functions (accept engine parameter)
# =============================================================================


async def check_db_connection(engine: AsyncEngine) -> None:
    """Verify database is reachable with a timeout guard.

    Raises:
        TimeoutError: If the check exceeds 30 seconds.
        Exception: If the database is unreachable.
    """
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
    """Verify Azure AD token acquisition is working.

    This is a deeper health check than check_db_connection() - it validates
    that the managed identity can obtain tokens, which is useful for
    diagnosing auth issues separately from database connectivity.

    Returns:
        True if token was acquired successfully.

    Raises:
        Exception if token acquisition fails.
    """
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
        except Exception as e:
            set_wide_event_fields(
                db_error="azure_token_health_check_failed",
                db_error_detail=str(e),
            )
            result["azure_auth"] = False
            # Don't proceed to DB check if auth is broken
            return result

    try:
        await check_db_connection(engine)
        result["database"] = True
    except Exception as e:
        set_wide_event_fields(
            db_error="health_check_failed",
            db_error_detail=str(e),
        )
        result["database"] = False

    result["pool"] = get_pool_status(engine)

    return result


# =============================================================================
# Testing Utilities
# =============================================================================


async def reset_azure_credential() -> None:
    """For testing — resets cached credential (lock-protected)."""
    await _reset_azure_credential()
