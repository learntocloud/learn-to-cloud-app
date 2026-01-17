"""Pytest fixtures for API tests.

Provides isolated test database and async session fixtures.
"""

import asyncio
from collections.abc import AsyncGenerator
from datetime import UTC, datetime
from typing import Any

import pytest
import pytest_asyncio
from sqlalchemy import event
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from core.database import Base
from models import (
    QuestionAttempt,
    StepProgress,
    Submission,
    SubmissionType,
    User,
)
from services.hands_on_verification import get_requirements_for_phase
from services.progress import PHASE_REQUIREMENTS

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
        poolclass=StaticPool,
        echo=False,
    )

    @event.listens_for(engine.sync_engine, "connect")
    def set_sqlite_pragma(dbapi_connection: Any, connection_record: Any) -> None:
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    yield engine

    await engine.dispose()


@pytest_asyncio.fixture(scope="function")
async def db_session(test_engine) -> AsyncGenerator[AsyncSession]:
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


async def _add_submissions_for_phase(
    db: AsyncSession, user_id: str, phase_id: int
) -> None:
    """Add validated submissions for all requirements in a phase."""
    requirements = get_requirements_for_phase(phase_id)
    for req in requirements:
        submission = Submission(
            user_id=user_id,
            requirement_id=req.id,
            submission_type=SubmissionType.GITHUB_PROFILE,
            phase_id=phase_id,
            submitted_value="https://github.com/testuser/test",
            extracted_username="testuser",
            is_validated=True,
            validated_at=datetime.now(UTC),
        )
        db.add(submission)


@pytest_asyncio.fixture
async def test_user_with_progress(db_session: AsyncSession, test_user: User) -> User:
    """Create a test user with some phase progress.

    Adds passed questions, steps, and GitHub submissions for 3 complete phases.
    """
    for phase_id in [0, 1, 2]:
        req = PHASE_REQUIREMENTS[phase_id]

        for step_num in range(req.steps):
            step = StepProgress(
                user_id=test_user.id,
                topic_id=f"phase{phase_id}-topic{step_num // 3}",
                step_order=(step_num % 3) + 1,
            )
            db_session.add(step)

        for q_num in range(req.questions):
            topic_num = q_num // 2
            q_in_topic = (q_num % 2) + 1
            attempt = QuestionAttempt(
                user_id=test_user.id,
                topic_id=f"phase{phase_id}-topic{topic_num}",
                question_id=f"phase{phase_id}-topic{topic_num}-q{q_in_topic}",
                user_answer="Test answer",
                is_passed=True,
                llm_feedback="Good answer!",
            )
            db_session.add(attempt)

        await _add_submissions_for_phase(db_session, test_user.id, phase_id)

    await db_session.commit()
    return test_user


@pytest_asyncio.fixture
async def test_user_full_completion(db_session: AsyncSession, test_user: User) -> User:
    """Create a test user with all phases completed.

    Adds passed questions, steps, and GitHub submissions for all 7 phases.
    """
    for phase_id, req in PHASE_REQUIREMENTS.items():
        for step_num in range(req.steps):
            step = StepProgress(
                user_id=test_user.id,
                topic_id=f"phase{phase_id}-topic{step_num // 3}",
                step_order=(step_num % 3) + 1,
            )
            db_session.add(step)

        for q_num in range(req.questions):
            topic_num = q_num // 2
            q_in_topic = (q_num % 2) + 1
            attempt = QuestionAttempt(
                user_id=test_user.id,
                topic_id=f"phase{phase_id}-topic{topic_num}",
                question_id=f"phase{phase_id}-topic{topic_num}-q{q_in_topic}",
                user_answer="Test answer",
                is_passed=True,
                llm_feedback="Good answer!",
            )
            db_session.add(attempt)

        await _add_submissions_for_phase(db_session, test_user.id, phase_id)

    await db_session.commit()
    return test_user


# =============================================================================
# HTTP CLIENT FIXTURE
# =============================================================================


@pytest.fixture
def client(db_session: AsyncSession, test_user: User):
    """Create a FastAPI TestClient with mocked authentication.

    This fixture provides a TestClient that automatically authenticates
    requests as the test_user. It overrides the require_auth dependency
    to bypass real authentication.
    """
    from fastapi.testclient import TestClient

    from core.auth import require_auth
    from main import app

    # Override auth to return test user ID
    def override_require_auth():
        return test_user.id

    app.dependency_overrides[require_auth] = override_require_auth

    with TestClient(app) as test_client:
        yield test_client

    # Clean up overrides
    app.dependency_overrides.clear()


# =============================================================================
# MOCK EXTERNAL SERVICE FIXTURES
# =============================================================================


@pytest.fixture
def mock_openai_api():
    """Mock OpenAI API responses for LLM question evaluation."""
    from unittest.mock import AsyncMock

    mock = AsyncMock()

    # Default: return passing evaluation
    mock.create_completion.return_value = {
        "choices": [
            {
                "message": {
                    "content": (
                        '{"is_passed": true, '
                        '"feedback": "Great answer! You demonstrated '
                        'understanding of key concepts."}'
                    )
                }
            }
        ]
    }

    return mock


# =============================================================================
# PERFORMANCE TESTING FIXTURES
# =============================================================================


@pytest.fixture
def benchmark_threshold():
    """Standard performance thresholds for benchmarking."""
    return {
        "fast": 0.05,  # 50ms
        "medium": 0.2,  # 200ms
        "slow": 1.0,  # 1 second
    }


@pytest_asyncio.fixture
async def large_dataset_user(db_session: AsyncSession) -> User:
    """User with large amount of progress data for performance testing."""
    user = User(
        id="large_data_user",
        email="largedata@test.com",
        first_name="Large",
        last_name="Data",
        github_username="largedata",
    )
    db_session.add(user)
    await db_session.commit()

    # Add 1000 step completions
    for i in range(1000):
        step = StepProgress(
            user_id=user.id,
            topic_id=f"phase{i % 7}-topic{i % 10}",
            step_order=(i % 10) + 1,
        )
        db_session.add(step)

    # Add 500 question attempts
    for i in range(500):
        attempt = QuestionAttempt(
            user_id=user.id,
            topic_id=f"phase{i % 7}-topic{i % 10}",
            question_id=f"phase{i % 7}-topic{i % 10}-q{i % 5}",
            user_answer=f"Answer {i}",
            is_passed=i % 2 == 0,  # 50% pass rate
            llm_feedback="Feedback",
        )
        db_session.add(attempt)

    await db_session.commit()
    return user


# =============================================================================
# CUSTOM PYTEST MARKERS
# =============================================================================


def pytest_configure(config):
    """Register custom markers."""
    config.addinivalue_line(
        "markers", "integration: marks tests as integration tests (slow)"
    )
    config.addinivalue_line(
        "markers", "performance: marks tests as performance benchmarks"
    )
    config.addinivalue_line("markers", "security: marks tests as security tests")
    config.addinivalue_line(
        "markers", "external: marks tests that require external services"
    )
