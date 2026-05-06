"""Pytest configuration and shared fixtures."""

import os
from collections.abc import AsyncGenerator

os.environ.setdefault(
    "DATABASE_URL",
    "postgresql+asyncpg://postgres:postgres@db:5432/test_learn_to_cloud",
)
os.environ.setdefault("GITHUB_TOKEN", "test_github_token")
os.environ.setdefault("LABS_VERIFICATION_SECRET", "test_ctf_secret_must_be_32_chars!")
os.environ.setdefault("DEBUG", "true")

import pytest
import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.pool import NullPool

from learn_to_cloud_shared.core.config import Settings
from learn_to_cloud_shared.core.database import Base


def _build_test_database_url() -> tuple[str, str, int]:
    """Derive the isolated test database URL from DATABASE_URL."""
    from sqlalchemy.engine import make_url

    raw = os.environ.get(
        "DATABASE_URL",
        "postgresql+asyncpg://postgres:postgres@db:5432/test_learn_to_cloud",
    )
    url = make_url(raw)
    host = url.host or "localhost"
    port = url.port or 5432
    test_url = url.set(database="test_learn_to_cloud", host=host, port=port)
    return test_url.render_as_string(hide_password=False), host, port


TEST_DATABASE_URL, _DB_HOST, _DB_PORT = _build_test_database_url()
_DB_AVAILABLE: bool | None = None


@pytest.fixture(scope="session")
def test_settings() -> Settings:
    """Create test settings pointing to the test database."""
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


def _check_db_available() -> bool:
    """Check whether PostgreSQL is available."""
    global _DB_AVAILABLE
    if _DB_AVAILABLE is not None:
        return _DB_AVAILABLE

    import socket

    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(1)
        result = sock.connect_ex((_DB_HOST, _DB_PORT))
        sock.close()
        _DB_AVAILABLE = result == 0
    except Exception:
        _DB_AVAILABLE = False

    return _DB_AVAILABLE


@pytest_asyncio.fixture(scope="session")
async def test_engine() -> AsyncGenerator[AsyncEngine]:
    """Create the test database engine."""
    if not _check_db_available():
        pytest.fail("PostgreSQL not available - is the database running?")

    admin_url = TEST_DATABASE_URL.rsplit("/", 1)[0] + "/postgres"
    admin_engine = create_async_engine(
        admin_url,
        poolclass=NullPool,
        isolation_level="AUTOCOMMIT",
    )

    async with admin_engine.connect() as conn:
        result = await conn.execute(
            text("SELECT 1 FROM pg_database WHERE datname = 'test_learn_to_cloud'")
        )
        if not result.scalar():
            await conn.execute(text("CREATE DATABASE test_learn_to_cloud"))

    await admin_engine.dispose()

    engine = create_async_engine(
        TEST_DATABASE_URL,
        poolclass=NullPool,
        echo=False,
    )

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)

    yield engine

    await engine.dispose()


@pytest_asyncio.fixture(scope="function")
async def db_session(
    test_engine: AsyncEngine,
) -> AsyncGenerator[AsyncSession]:
    """Create a test database session with transaction rollback."""
    connection = await test_engine.connect()
    transaction = await connection.begin()
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
        await transaction.rollback()
        await connection.close()


def _quote_table_name(name: str) -> str:
    return ".".join(f'"{part}"' for part in name.split("."))


@pytest_asyncio.fixture(autouse=True)
async def cleanup_database(request: pytest.FixtureRequest):
    """Truncate tables after integration tests."""
    yield

    if request.node.get_closest_marker("integration") is None:
        return

    if not _check_db_available():
        pytest.fail("PostgreSQL not available - is the database running?")

    engine: AsyncEngine = request.getfixturevalue("test_engine")
    table_names = [table.fullname for table in Base.metadata.sorted_tables]
    if not table_names:
        return

    quoted_tables = ", ".join(_quote_table_name(name) for name in table_names)
    async with engine.begin() as conn:
        await conn.execute(text(f"TRUNCATE {quoted_tables} RESTART IDENTITY CASCADE"))
