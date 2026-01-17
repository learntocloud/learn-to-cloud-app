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
from typing import Annotated, NamedTuple

from fastapi import Depends
from sqlalchemy import event, text
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase
from sqlalchemy.pool import NullPool, QueuePool
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

_azure_credential = None


class Base(DeclarativeBase):
    """Base class for all SQLAlchemy models."""

    pass


_engine: AsyncEngine | None = None
_async_session_maker: async_sessionmaker[AsyncSession] | None = None


def _get_azure_credential():
    """Get or create the cached DefaultAzureCredential instance.

    Note: The credential object is reused, but tokens are fetched fresh
    per connection to handle expiration (~1 hour).
    """
    global _azure_credential
    if _azure_credential is None:
        from azure.identity import DefaultAzureCredential

        _azure_credential = DefaultAzureCredential()
    return _azure_credential


def _reset_azure_credential() -> None:
    """Reset the Azure credential (useful if token acquisition starts failing)."""
    global _azure_credential
    _azure_credential = None


@retry(
    stop=stop_after_attempt(_AZURE_RETRY_ATTEMPTS),
    wait=wait_exponential(
        multiplier=1, min=_AZURE_RETRY_MIN_WAIT, max=_AZURE_RETRY_MAX_WAIT
    ),
    retry=retry_if_exception_type(Exception),
    before_sleep=before_sleep_log(logger, logging.WARNING),
    reraise=True,
)
def _get_azure_token_sync() -> str:
    """Get an Azure AD token for PostgreSQL authentication (sync, may block).

    Includes retry logic for transient Azure AD failures (e.g., IMDS timeouts,
    network blips). Retries up to 3 times with exponential backoff.
    """
    credential = _get_azure_credential()
    token = credential.get_token("https://ossrdbms-aad.database.windows.net/.default")
    return token.token


async def _get_azure_token() -> str:
    """Get Azure AD token for PostgreSQL auth without blocking event loop.

    Includes a timeout to prevent hanging if Azure AD is unresponsive.
    """
    try:
        async with asyncio.timeout(_AZURE_TOKEN_TIMEOUT):
            return await asyncio.to_thread(_get_azure_token_sync)
    except TimeoutError:
        logger.error(
            f"Azure AD token acquisition timed out after {_AZURE_TOKEN_TIMEOUT}s"
        )
        raise


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

    Note: connect_args from create_async_engine is bypassed when using async_creator,
    so we must set server_settings (like statement_timeout) directly here.

    Raises:
        TimeoutError: If token acquisition or connection takes too long.
        asyncpg.PostgresError: If connection fails after token is obtained.
    """
    settings = get_settings()

    try:
        token = await _get_azure_token()
    except TimeoutError:
        # Reset credential in case it's in a bad state
        _reset_azure_credential()
        raise

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

        if settings.use_azure_postgres:
            database_url = _build_azure_database_url()
            is_sqlite = False
            async_creator = _azure_asyncpg_creator
        else:
            database_url = settings.database_url
            is_sqlite = "sqlite" in database_url
            async_creator = None

        _engine = create_async_engine(
            database_url,
            echo=settings.db_echo,  # Explicit control - default off (very verbose)
            poolclass=NullPool if is_sqlite else None,
            **(
                {}
                if is_sqlite
                else {
                    "pool_size": settings.db_pool_size,
                    "max_overflow": settings.db_pool_max_overflow,
                    "pool_timeout": settings.db_pool_timeout,
                    "pool_recycle": settings.db_pool_recycle,
                    "pool_pre_ping": True,
                    "connect_args": {
                        "server_settings": {
                            "statement_timeout": str(settings.db_statement_timeout_ms)
                        }
                    },
                }
            ),
            **({} if async_creator is None else {"async_creator": async_creator}),
        )

        if is_sqlite:

            @event.listens_for(_engine.sync_engine, "connect")
            def _set_sqlite_pragma(dbapi_connection, connection_record) -> None:
                cursor = dbapi_connection.cursor()
                cursor.execute("PRAGMA foreign_keys=ON")
                cursor.close()

        # Add pool event listeners for monitoring (PostgreSQL only)
        if not is_sqlite:
            _setup_pool_event_listeners(_engine)

        try:
            from .telemetry import instrument_sqlalchemy_engine

            instrument_sqlalchemy_engine(_engine)
        except Exception as e:
            logger.warning(f"Failed to instrument SQLAlchemy for telemetry: {e}")

    return _engine


def _setup_pool_event_listeners(engine: AsyncEngine) -> None:
    """Set up connection pool event listeners for monitoring.

    Logs pool checkout/checkin events at DEBUG level and warnings when
    the pool is under pressure (overflow connections being used).
    """
    pool = engine.sync_engine.pool

    @event.listens_for(pool, "checkout")
    def _on_checkout(dbapi_conn, connection_record, connection_proxy):
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


async def get_db() -> AsyncGenerator[AsyncSession]:
    """
    FastAPI dependency that provides a database session.

    Handles transaction lifecycle automatically:
    - Commits on successful completion (no-op for read-only requests)
    - Rolls back on any exception

    Usage:
        @app.get("/items")
        async def get_items(db: DbSession):
            result = await db.execute(select(Item))
            return result.scalars().all()

    Notes:
        - Use flush() within a request if you need auto-generated IDs
        - Use refresh() after flush if you need DB-side defaults
        - Do NOT call commit() in route handlers - this dependency handles it
    """
    session_maker = get_session_maker()
    async with session_maker() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


DbSession = Annotated[AsyncSession, Depends(get_db)]


async def init_db() -> None:
    """Verify database connectivity at startup.

    This only checks that the database is reachable. Schema management should be
    handled separately via migrations or the create_tables() function.
    """
    engine = get_engine()

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


async def check_db_connection() -> None:
    """Verify the database is reachable.

    Raises:
        Exception if the database can't be reached.
    """
    engine = get_engine()
    async with engine.connect() as conn:
        await conn.execute(text("SELECT 1"))


class PoolStatus(NamedTuple):
    """Connection pool status for health checks."""

    pool_size: int
    checked_out: int
    overflow: int
    checked_in: int


def get_pool_status() -> PoolStatus | None:
    """Get current connection pool status.

    Returns:
        PoolStatus with pool metrics, or None if using NullPool/SQLite.
    """
    engine = get_engine()
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


async def comprehensive_health_check() -> dict:
    """Run comprehensive health checks for all database components.

    Returns:
        Dict with health status for each component:
        - database: bool - Can execute queries
        - azure_auth: bool | None - Token acquisition (None if not using Azure)
        - pool: PoolStatus | None - Pool metrics (None if using NullPool)
    """
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
        await check_db_connection()
        result["database"] = True
    except Exception as e:
        logger.error(f"Database health check failed: {e}")
        result["database"] = False

    # Get pool status
    result["pool"] = get_pool_status()

    return result


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
    global _engine, _async_session_maker, _azure_credential
    _engine = None
    _async_session_maker = None
    _azure_credential = None
