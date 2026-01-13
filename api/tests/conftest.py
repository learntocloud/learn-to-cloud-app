"""Pytest fixtures for API tests.

Provides isolated test database and async session fixtures.
"""

import asyncio
from collections.abc import AsyncGenerator
from typing import Any

import pytest
import pytest_asyncio
from sqlalchemy import event
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from shared.database import Base
from shared.models import Certificate, QuestionAttempt, User


# Use in-memory SQLite for tests (isolated from dev database)
TEST_DATABASE_URL = "sqlite+aiosqlite:///:memory:"


@pytest.fixture(scope="session")
def event_loop():
    """Create event loop for async tests."""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


@pytest_asyncio.fixture(scope="function")
async def test_engine():
    """Create a fresh in-memory database engine for each test."""
    engine = create_async_engine(
        TEST_DATABASE_URL,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,  # Required for in-memory SQLite with async
        echo=False,
    )
    
    # Enable foreign keys for SQLite
    @event.listens_for(engine.sync_engine, "connect")
    def set_sqlite_pragma(dbapi_connection: Any, connection_record: Any) -> None:
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()
    
    # Create all tables
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    
    yield engine
    
    # Cleanup
    await engine.dispose()


@pytest_asyncio.fixture(scope="function")
async def db_session(test_engine) -> AsyncGenerator[AsyncSession, None]:
    """Provide a database session for each test.
    
    Each test gets a fresh database with all tables created.
    Changes are automatically rolled back after each test.
    """
    session_maker = async_sessionmaker(
        test_engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )
    
    async with session_maker() as session:
        yield session
        # Rollback any uncommitted changes
        await session.rollback()


@pytest_asyncio.fixture
async def test_user(db_session: AsyncSession) -> User:
    """Create a test user in the database."""
    user = User(
        id="test_user_123",
        email="test@example.com",
        first_name="Test",
        last_name="User",
        github_username="testuser",
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return user


@pytest_asyncio.fixture
async def test_user_with_progress(db_session: AsyncSession, test_user: User) -> User:
    """Create a test user with some question progress.
    
    Adds passed questions for phase0 topics (simulating partial completion).
    """
    # Add passed questions for 3 topics in phase0 (2 questions each = 6 questions)
    topics = ["phase0-linux", "phase0-networking", "phase0-programming"]
    for topic_id in topics:
        for q_num in [1, 2]:
            attempt = QuestionAttempt(
                user_id=test_user.id,
                topic_id=topic_id,
                question_id=f"{topic_id}-q{q_num}",
                user_answer="Test answer",
                is_passed=True,
                llm_feedback="Good answer!",
            )
            db_session.add(attempt)
    
    await db_session.commit()
    return test_user


@pytest_asyncio.fixture
async def test_user_full_completion(db_session: AsyncSession, test_user: User) -> User:
    """Create a test user with all topics completed.
    
    Adds passed questions for all 40 topics (2 questions each = 80 questions).
    """
    # All topics across all phases
    all_topics = [
        # Phase 0
        "phase0-linux", "phase0-networking", "phase0-programming",
        "phase0-cloud-computing", "phase0-cloud-engineer", "phase0-devops",
        # Phase 1
        "phase1-cli-basics", "phase1-cloud-cli", "phase1-ctf-lab",
        "phase1-iac", "phase1-ssh", "phase1-version-control",
        # Phase 2
        "phase2-python", "phase2-apis", "phase2-databases",
        "phase2-fastapi", "phase2-genai-apis", "phase2-prompt-engineering",
        "phase2-build-the-app",
        # Phase 3
        "phase3-vms-compute", "phase3-cloud-networking", "phase3-security-iam",
        "phase3-database-deployment", "phase3-fastapi-deployment",
        "phase3-billing-cost-management", "phase3-secure-remote-access",
        "phase3-cloud-ai-services", "phase3-capstone",
        # Phase 4
        "phase4-containers", "phase4-container-orchestration", "phase4-cicd",
        "phase4-infrastructure-as-code", "phase4-monitoring-observability",
        "phase4-capstone",
        # Phase 5
        "phase5-identity-access-management", "phase5-network-security",
        "phase5-data-protection-secrets", "phase5-security-monitoring",
        "phase5-threat-detection-response", "phase5-capstone",
    ]
    
    for topic_id in all_topics:
        for q_num in [1, 2]:
            attempt = QuestionAttempt(
                user_id=test_user.id,
                topic_id=topic_id,
                question_id=f"{topic_id}-q{q_num}",
                user_answer="Test answer",
                is_passed=True,
                llm_feedback="Good answer!",
            )
            db_session.add(attempt)
    
    await db_session.commit()
    return test_user
