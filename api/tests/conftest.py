"""Pytest configuration and shared fixtures.

This module provides:
- Test database setup with real PostgreSQL (via Docker)
- Async session fixtures for repository/service tests
- FastAPI test client for route integration tests

Architecture follows best practices from:
- https://pythonspeed.com/articles/faster-db-tests/
- https://pythonspeed.com/articles/verified-fakes/
"""

# Set environment variables BEFORE any imports that trigger Settings validation
import os

os.environ.setdefault(
    "DATABASE_URL",
    "postgresql+asyncpg://postgres:postgres@localhost:5432/test_learn_to_cloud",
)
os.environ.setdefault("GITHUB_TOKEN", "test_github_token")
os.environ.setdefault("LABS_VERIFICATION_SECRET", "test_ctf_secret_must_be_32_chars!")
os.environ.setdefault("DEBUG", "true")

from collections.abc import AsyncGenerator

import pytest
import pytest_asyncio
from fastapi import FastAPI
from sqlalchemy import text
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.pool import NullPool

from core.config import Settings
from core.database import Base

# =============================================================================
# Test Settings
# =============================================================================

# Test database URL - uses same PostgreSQL from docker-compose
TEST_DATABASE_URL = (
    "postgresql+asyncpg://postgres:postgres@localhost:5432/test_learn_to_cloud"
)


@pytest.fixture(scope="session")
def test_settings() -> Settings:
    """Create test settings pointing to test database.

    Uses the same PostgreSQL instance from docker-compose but a separate database.
    """
    return Settings(
        database_url=TEST_DATABASE_URL,
        debug=True,
        require_https=False,
        github_client_id="test_github_client_id",
        github_client_secret="test_github_client_secret",
        session_secret_key="test_session_secret_key_for_testing",
        github_token="test_github_token",
        labs_verification_secret="test_ctf_secret_must_be_32_chars!",
        cors_allowed_origins="",
    )


# =============================================================================
# Database Fixtures
# =============================================================================

# Check if database is available (skip DB tests in CI without database)
_DB_AVAILABLE = None


def _check_db_available() -> bool:
    """Check if PostgreSQL is available. Cached after first check."""
    global _DB_AVAILABLE
    if _DB_AVAILABLE is not None:
        return _DB_AVAILABLE

    import socket

    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(1)
        result = sock.connect_ex(("localhost", 5432))
        sock.close()
        _DB_AVAILABLE = result == 0
    except Exception:
        _DB_AVAILABLE = False

    return _DB_AVAILABLE


@pytest_asyncio.fixture(scope="session")
async def test_engine() -> AsyncGenerator[AsyncEngine]:
    """Create test database engine.

    Creates the test database if it doesn't exist and sets up tables once
    per test session for faster runs.
    """
    if not _check_db_available():
        pytest.skip("PostgreSQL not available - skipping database test")

    # Connect to default database to create test database if needed
    admin_engine = create_async_engine(
        "postgresql+asyncpg://postgres:postgres@localhost:5432/postgres",
        poolclass=NullPool,
        isolation_level="AUTOCOMMIT",
    )

    async with admin_engine.connect() as conn:
        # Check if test database exists
        result = await conn.execute(
            text("SELECT 1 FROM pg_database WHERE datname = 'test_learn_to_cloud'")
        )
        if not result.scalar():
            await conn.execute(text("CREATE DATABASE test_learn_to_cloud"))

    await admin_engine.dispose()

    # Create engine for test database
    engine = create_async_engine(
        TEST_DATABASE_URL,
        poolclass=NullPool,
        echo=False,
    )

    # Recreate all tables to ensure schema matches current models
    async with engine.begin() as conn:
        await conn.execute(text("DROP TABLE IF EXISTS question_attempts CASCADE"))
        await conn.execute(text("DROP TABLE IF EXISTS user_scenarios CASCADE"))
        await conn.execute(text("DROP TABLE IF EXISTS user_activities CASCADE"))
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)

    yield engine

    await engine.dispose()


@pytest_asyncio.fixture(scope="function")
async def db_session(
    test_engine: AsyncEngine,
) -> AsyncGenerator[AsyncSession]:
    """Create a test database session with transaction rollback.

    Each test runs in a transaction that's rolled back at the end,
    ensuring test isolation without the overhead of recreating tables.
    """
    # Create a connection for this test
    connection = await test_engine.connect()

    # Begin a transaction that we'll roll back
    transaction = await connection.begin()

    # Create a session bound to this connection
    async_session_factory = async_sessionmaker(
        bind=connection,
        class_=AsyncSession,
        expire_on_commit=False,
        autoflush=False,
    )

    session = async_session_factory()

    try:
        yield session
    finally:
        await session.close()
        # Rollback the transaction - all test data disappears
        await transaction.rollback()
        await connection.close()


def _quote_table_name(name: str) -> str:
    return ".".join(f'"{part}"' for part in name.split("."))


@pytest_asyncio.fixture(autouse=True)
async def cleanup_database(
    request: pytest.FixtureRequest,
):
    """Truncate tables after integration tests to keep data isolated.

    Only requests `test_engine` when an integration marker is present,
    so pure unit tests never trigger the database session fixture.
    """
    yield

    if request.node.get_closest_marker("integration") is None:
        return

    if not _check_db_available():
        return

    engine: AsyncEngine = request.getfixturevalue("test_engine")

    table_names = [table.fullname for table in Base.metadata.sorted_tables]
    if not table_names:
        return

    quoted_tables = ", ".join(_quote_table_name(name) for name in table_names)
    async with engine.begin() as conn:
        await conn.execute(text(f"TRUNCATE {quoted_tables} RESTART IDENTITY CASCADE"))


# =============================================================================
# FastAPI Test Client Fixtures
# =============================================================================


@pytest_asyncio.fixture(scope="function")
async def app(
    test_engine: AsyncEngine,
) -> AsyncGenerator[FastAPI]:
    """Create FastAPI app configured for testing.

    - Uses test database
    """
    # Import here to avoid circular imports and ensure fresh app state
    from main import app as fastapi_app

    # Store test engine and session maker in app state
    fastapi_app.state.engine = test_engine
    fastapi_app.state.session_maker = async_sessionmaker(
        bind=test_engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )
    fastapi_app.state.init_done = True
    fastapi_app.state.init_error = None

    yield fastapi_app
