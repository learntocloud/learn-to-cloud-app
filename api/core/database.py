"""Database connection and session management.

Uses SQLAlchemy 2.0 async patterns with FastAPI app.state for lifecycle.
Engine and session maker are created at startup and stored in app.state.

Supports two authentication modes:
- Local development: PostgreSQL with password authentication (Docker container)
- Azure: PostgreSQL with managed identity (passwordless) authentication

Architecture:
- FastAPI app.state holds engine and session_maker (created in lifespan)
- get_db() dependency accesses state via Request
- Health checks access state via Request
"""

import asyncio
import logging
from collections.abc import AsyncGenerator
from typing import Annotated, NamedTuple

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
from tenacity import (
    before_sleep_log,
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from core.config import get_settings

logger = logging.getLogger(__name__)

# Timeout for Azure AD token acquisition (seconds)
_AZURE_TOKEN_TIMEOUT = 30

# Retry configuration for transient Azure failures
_AZURE_RETRY_ATTEMPTS = 3
_AZURE_RETRY_MIN_WAIT = 1  # seconds
_AZURE_RETRY_MAX_WAIT = 10  # seconds

# Azure PostgreSQL OAuth scope
_AZURE_PG_SCOPE = "https://ossrdbms-aad.database.windows.net/.default"

# Module-level credential cache (stateless - just caches the credential object)
_azure_credential = None


class Base(DeclarativeBase):
    pass


class PoolStatus(NamedTuple):
    """Connection pool status for health checks."""

    pool_size: int
    checked_out: int
    overflow: int
    checked_in: int


# =============================================================================
# Azure Token Acquisition
# =============================================================================


def _get_azure_credential():
    # Credential reused, but tokens fetched fresh per connection (~1 hour expiry)
    global _azure_credential
    if _azure_credential is None:
        from azure.identity import DefaultAzureCredential

        _azure_credential = DefaultAzureCredential()
    return _azure_credential


def _reset_azure_credential() -> None:
    global _azure_credential
    _azure_credential = None


def _get_azure_token_sync() -> str:
    """Get an Azure AD token for PostgreSQL authentication (sync, may block).

    Note: Retry logic is handled by the async wrapper to properly coordinate
    with asyncio timeout and credential reset.
    """
    credential = _get_azure_credential()
    token = credential.get_token(_AZURE_PG_SCOPE)
    return token.token


@retry(
    stop=stop_after_attempt(_AZURE_RETRY_ATTEMPTS),
    wait=wait_exponential(
        multiplier=1, min=_AZURE_RETRY_MIN_WAIT, max=_AZURE_RETRY_MAX_WAIT
    ),
    # Retry on transient failures only - not programming errors
    # TimeoutError: token acquisition timeout
    # OSError: network issues (includes ConnectionError, socket errors)
    retry=retry_if_exception_type((TimeoutError, OSError)),
    before_sleep=before_sleep_log(logger, logging.WARNING),
    reraise=True,
)
async def _get_azure_token() -> str:
    """Get Azure AD token for PostgreSQL auth without blocking event loop.

    Includes retry logic with exponential backoff for transient failures
    (IMDS timeouts, network blips) and a per-attempt timeout.
    """
    try:
        async with asyncio.timeout(_AZURE_TOKEN_TIMEOUT):
            return await asyncio.to_thread(_get_azure_token_sync)
    except TimeoutError:
        logger.warning(
            f"Azure AD token acquisition timed out after {_AZURE_TOKEN_TIMEOUT}s, "
            "will retry if attempts remaining"
        )
        # Reset credential on timeout in case it's in a bad state
        _reset_azure_credential()
        raise


# =============================================================================
# Engine Creation (called once at startup)
# =============================================================================


def _build_azure_database_url() -> str:
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
            port=5432,
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
        logger.error(
            f"Failed to connect to Azure PostgreSQL at {settings.postgres_host}: {e}"
        )
        raise


def _setup_pool_event_listeners(engine: AsyncEngine) -> None:
    # Note: AsyncAdaptedQueuePool is a subclass of QueuePool
    pool = engine.sync_engine.pool

    @event.listens_for(pool, "checkout")
    def _on_checkout(dbapi_conn, connection_record, connection_proxy):
        # isinstance check provides proper type narrowing for the type checker
        if isinstance(pool, QueuePool):
            checked_out = pool.checkedout()
            overflow = pool.overflow()
            pool_size = pool.size()
            if overflow > 0:
                logger.warning(
                    f"Pool using overflow connections: "
                    f"{checked_out}/{pool_size} (+{overflow} overflow)"
                )
            else:
                logger.debug(
                    f"Pool checkout: {checked_out}/{pool_size} connections in use"
                )

    @event.listens_for(pool, "checkin")
    def _on_checkin(dbapi_conn, connection_record):
        if isinstance(pool, QueuePool):
            logger.debug(
                f"Pool checkin: {pool.checkedout()}/{pool.size()} connections in use"
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
        "pool_pre_ping": True,
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
        logger.warning(f"Failed to instrument SQLAlchemy for telemetry: {e}")

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
            await session.rollback()
            raise


DbSession = Annotated[AsyncSession, Depends(get_db)]


# =============================================================================
# Lifecycle Functions (called from lifespan)
# =============================================================================


async def init_db(engine: AsyncEngine) -> None:
    """Verify database is reachable. Schema managed via migrations."""
    logger.info("Verifying database connectivity...")

    try:
        async with asyncio.timeout(30):
            async with engine.connect() as conn:
                await conn.execute(text("SELECT 1"))
        logger.info("Database connection verified")
    except TimeoutError:
        logger.error("Database connection timed out after 30 seconds")
        raise
    except Exception as e:
        logger.error(f"Database connection failed: {e}")
        raise


async def dispose_engine(engine: AsyncEngine) -> None:
    await engine.dispose()
    logger.info("Database engine disposed")


# =============================================================================
# Health Check Functions (accept engine parameter)
# =============================================================================


async def check_db_connection(engine: AsyncEngine) -> None:
    async with engine.connect() as conn:
        await conn.execute(text("SELECT 1"))


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
        # Not using Azure auth, skip this check
        return True

    # This will raise on failure (with retry)
    await _get_azure_token()
    return True


async def comprehensive_health_check(engine: AsyncEngine) -> dict:
    """Returns {database: bool, azure_auth: bool|None, pool: PoolStatus|None}."""
    settings = get_settings()
    result: dict = {
        "database": False,
        "azure_auth": None,
        "pool": None,
    }

    # Check Azure auth first (if applicable)
    if settings.use_azure_postgres:
        try:
            await check_azure_token_acquisition()
            result["azure_auth"] = True
        except Exception as e:
            logger.error(f"Azure token acquisition health check failed: {e}")
            result["azure_auth"] = False
            # Don't proceed to DB check if auth is broken
            return result

    # Check database connectivity
    try:
        await check_db_connection(engine)
        result["database"] = True
    except Exception as e:
        logger.error(f"Database health check failed: {e}")
        result["database"] = False

    # Get pool status
    result["pool"] = get_pool_status(engine)

    return result


# =============================================================================
# Testing Utilities
# =============================================================================


def reset_azure_credential() -> None:
    """For testing."""
    global _azure_credential
    _azure_credential = None
