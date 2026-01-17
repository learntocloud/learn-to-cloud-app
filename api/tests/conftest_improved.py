"""IMPROVED pytest fixtures for API tests.

Additions over original conftest.py:
- Parameterized user fixtures (new user, partial progress, full progress)
- Phase-specific fixtures
- Mock external service fixtures (GitHub, OpenAI)
- Performance testing fixtures
- Better database session management
"""

import asyncio
from collections.abc import AsyncGenerator
from datetime import UTC, datetime
from typing import Any
from unittest.mock import AsyncMock, Mock

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


# =============================================================================
# ENGINE AND SESSION FIXTURES (Original - Keep)
# =============================================================================


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
    """Provide a database session for each test."""
    session_maker = async_sessionmaker(
        test_engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )

    async with session_maker() as session:
        yield session
        await session.rollback()


# =============================================================================
# IMPROVED USER FIXTURES
# =============================================================================


@pytest_asyncio.fixture
async def test_user(db_session: AsyncSession) -> User:
    """Create a basic test user (original - keep for backward compatibility)."""
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
async def user_no_github(db_session: AsyncSession) -> User:
    """Create user without GitHub username (for testing that scenario)."""
    user = User(
        id="user_no_github",
        email="nogithub@example.com",
        first_name="No",
        last_name="GitHub",
        github_username=None,  # Explicitly null
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return user


@pytest_asyncio.fixture
async def admin_user(db_session: AsyncSession) -> User:
    """Create an admin user for testing admin functionality."""
    user = User(
        id="admin_user_123",
        email="admin@example.com",
        first_name="Admin",
        last_name="User",
        github_username="adminuser",
        is_admin=True,
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return user


# =============================================================================
# PROGRESS-BASED USER FIXTURES (Improved)
# =============================================================================


@pytest_asyncio.fixture
async def user_phase_0_partial(db_session: AsyncSession) -> User:
    """User with partial progress in Phase 0 (not complete)."""
    user = User(
        id="user_p0_partial",
        email="p0partial@test.com",
        first_name="Partial",
        last_name="Zero",
        github_username="p0partial",
    )
    db_session.add(user)
    await db_session.commit()

    # Add some but not all requirements for Phase 0
    # Phase 0 requires: 15 steps, 12 questions, 1 hands-on

    # Complete only 10/15 steps
    for step_num in range(1, 11):
        step = StepProgress(
            user_id=user.id,
            topic_id="phase0-topic1",
            step_order=step_num,
        )
        db_session.add(step)

    # Pass only 6/12 questions
    for q_num in range(1, 7):
        attempt = QuestionAttempt(
            user_id=user.id,
            topic_id="phase0-topic1",
            question_id=f"phase0-topic1-q{q_num}",
            user_answer="Partial answer",
            is_passed=True,
            llm_feedback="Good!",
        )
        db_session.add(attempt)

    await db_session.commit()
    return user


@pytest_asyncio.fixture
async def user_phase_0_complete(db_session: AsyncSession) -> User:
    """User who has completed exactly Phase 0."""
    user = User(
        id="user_p0_complete",
        email="p0complete@test.com",
        first_name="Complete",
        last_name="Zero",
        github_username="p0complete",
    )
    db_session.add(user)
    await db_session.commit()

    # Complete ALL Phase 0 requirements
    req = PHASE_REQUIREMENTS[0]

    # Complete all 15 steps
    for step_num in range(1, req.steps + 1):
        step = StepProgress(
            user_id=user.id,
            topic_id="phase0-topic1",
            step_order=step_num,
        )
        db_session.add(step)

    # Pass all 12 questions
    for q_num in range(1, req.questions + 1):
        attempt = QuestionAttempt(
            user_id=user.id,
            topic_id="phase0-topic1",
            question_id=f"phase0-topic1-q{q_num}",
            user_answer="Complete answer",
            is_passed=True,
            llm_feedback="Excellent!",
        )
        db_session.add(attempt)

    # Add GitHub submission (hands-on)
    submission = Submission(
        user_id=user.id,
        requirement_id="phase0-github-profile",
        submission_type=SubmissionType.GITHUB_PROFILE,
        phase_id=0,
        submitted_value="https://github.com/p0complete",
        extracted_username="p0complete",
        is_validated=True,
        validated_at=datetime.now(UTC),
    )
    db_session.add(submission)

    await db_session.commit()
    return user


# Original fixtures (keep for backward compatibility)


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
    """Create a test user with some phase progress (original - keep)."""
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
    """Create a test user with all phases completed (original - keep)."""
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
# NEW: MOCK EXTERNAL SERVICE FIXTURES
# =============================================================================


@pytest.fixture
def mock_github_api():
    """Mock GitHub API responses for testing without hitting real API."""
    mock = Mock()

    # Mock successful repository fetch
    mock.get_repo.return_value = {
        "name": "test-repo",
        "owner": {"login": "testuser"},
        "html_url": "https://github.com/testuser/test-repo",
        "private": False,
    }

    # Mock user fetch
    mock.get_user.return_value = {
        "login": "testuser",
        "id": 12345,
        "avatar_url": "https://avatars.githubusercontent.com/u/12345",
    }

    return mock


@pytest.fixture
def mock_openai_api():
    """Mock OpenAI API responses for LLM question evaluation."""
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


@pytest.fixture
def mock_clerk_api():
    """Mock Clerk API for user authentication testing."""
    mock = Mock()

    # Mock user data
    mock.get_user.return_value = {
        "id": "user_clerk_123",
        "email_addresses": [{"email_address": "test@example.com"}],
        "first_name": "Test",
        "last_name": "User",
    }

    # Mock JWT verification
    mock.verify_token.return_value = {"sub": "user_clerk_123"}

    return mock


# =============================================================================
# NEW: PERFORMANCE TESTING FIXTURES
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
# NEW: CLEANUP MARKERS
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
