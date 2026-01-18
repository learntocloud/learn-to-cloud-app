"""Shared test fixtures for the Learn to Cloud test suite.

Provides:
- PostgreSQL database session fixtures with transaction rollback
- Model factories using factory-boy
- Faker instance for realistic test data
- Phase requirements fixtures
- PhaseProgress fixtures (empty, completed, partial, no hands-on)
- UserProgress fixtures (empty, completed)
- Submission fixtures (validated, unvalidated)
- Parameterized test data (phase IDs, streak thresholds)
"""

import os
from collections.abc import AsyncGenerator
from datetime import UTC, datetime

import factory
import pytest
from faker import Faker
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from core.config import get_settings
from core.database import Base
from models import (
    ActivityType,
    Certificate,
    ProcessedWebhook,
    QuestionAttempt,
    StepProgress,
    Submission,
    SubmissionType,
    User,
    UserActivity,
)
from services.phase_requirements_service import HandsOnRequirementData
from services.progress_service import PhaseProgress, UserProgress

# Initialize Faker for realistic data generation
fake = Faker()


# =============================================================================
# Database Fixtures - PostgreSQL with Transaction Rollback
# =============================================================================

# Test database URL - use PostgreSQL for realistic testing
# Locally: docker compose up db (port 5432)
# CI: GitHub Actions postgres service (port 5432)
TEST_DATABASE_URL = os.environ.get(
    "TEST_DATABASE_URL",
    "postgresql+asyncpg://postgres:postgres@localhost:5432/learn_to_cloud",
)


@pytest.fixture
async def db_session() -> AsyncGenerator[AsyncSession]:
    """Create a database session with transaction rollback.

    Each test gets its own engine, connection, and transaction.
    The transaction is rolled back after the test for isolation.
    Uses PostgreSQL for realistic testing (same as production).
    """
    from sqlalchemy.pool import NullPool

    # Create engine per test to avoid event loop issues
    engine = create_async_engine(
        TEST_DATABASE_URL,
        echo=False,
        poolclass=NullPool,  # No connection pooling for tests
    )

    # Create all tables
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    # Create a connection and start a transaction
    async with engine.connect() as conn:
        # Start a transaction
        await conn.begin()

        # Create session bound to this connection
        async_session_maker = async_sessionmaker(
            bind=conn,
            class_=AsyncSession,
            expire_on_commit=False,
        )

        async with async_session_maker() as session:
            yield session

        # Rollback the transaction (undo all changes from this test)
        await conn.rollback()

    # Dispose engine
    await engine.dispose()


@pytest.fixture
def clear_settings_cache():
    """Clear the settings cache before and after each test.

    This ensures tests can use different settings without interference.
    """
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


# =============================================================================
# Model Factories using factory-boy
# =============================================================================


class UserFactory(factory.Factory):
    """Factory for creating User instances."""

    class Meta:
        model = User

    id = factory.LazyFunction(lambda: fake.uuid4())
    email = factory.LazyFunction(lambda: fake.email())
    first_name = factory.LazyFunction(lambda: fake.first_name())
    last_name = factory.LazyFunction(lambda: fake.last_name())
    avatar_url = factory.LazyFunction(lambda: fake.image_url())
    github_username = factory.LazyFunction(lambda: fake.user_name())
    is_admin = False


class SubmissionFactory(factory.Factory):
    """Factory for creating Submission instances."""

    class Meta:
        model = Submission

    id = factory.Sequence(lambda n: n + 1)
    user_id = factory.LazyFunction(lambda: fake.uuid4())
    requirement_id = "phase0-github-profile"
    submission_type = SubmissionType.GITHUB_PROFILE
    phase_id = 0
    submitted_value = factory.LazyFunction(
        lambda: f"https://github.com/{fake.user_name()}"
    )
    extracted_username = factory.LazyFunction(lambda: fake.user_name())
    is_validated = True
    validated_at = factory.LazyFunction(lambda: datetime.now(UTC))


class StepProgressFactory(factory.Factory):
    """Factory for creating StepProgress instances."""

    class Meta:
        model = StepProgress

    id = factory.Sequence(lambda n: n + 1)
    user_id = factory.LazyFunction(lambda: fake.uuid4())
    topic_id = "phase0-topic1"
    step_order = factory.Sequence(lambda n: n)
    completed_at = factory.LazyFunction(lambda: datetime.now(UTC))


class QuestionAttemptFactory(factory.Factory):
    """Factory for creating QuestionAttempt instances."""

    class Meta:
        model = QuestionAttempt

    id = factory.Sequence(lambda n: n + 1)
    user_id = factory.LazyFunction(lambda: fake.uuid4())
    topic_id = "phase0-topic1"
    question_id = "phase0-topic1-q1"
    user_answer = factory.LazyFunction(lambda: fake.paragraph())
    is_passed = True
    llm_feedback = "Good answer!"
    confidence_score = 0.95
    created_at = factory.LazyFunction(lambda: datetime.now(UTC))


class UserActivityFactory(factory.Factory):
    """Factory for creating UserActivity instances."""

    class Meta:
        model = UserActivity

    id = factory.Sequence(lambda n: n + 1)
    user_id = factory.LazyFunction(lambda: fake.uuid4())
    activity_type = ActivityType.STEP_COMPLETE
    activity_date = factory.LazyFunction(lambda: datetime.now(UTC).date())
    reference_id = factory.LazyFunction(lambda: fake.uuid4())
    created_at = factory.LazyFunction(lambda: datetime.now(UTC))


class CertificateFactory(factory.Factory):
    """Factory for creating Certificate instances."""

    class Meta:
        model = Certificate

    id = factory.Sequence(lambda n: n + 1)
    user_id = factory.LazyFunction(lambda: fake.uuid4())
    certificate_type = "completion"
    verification_code = factory.LazyFunction(lambda: fake.sha256()[:64])
    recipient_name = factory.LazyFunction(lambda: fake.name())
    issued_at = factory.LazyFunction(lambda: datetime.now(UTC))
    phases_completed = 7
    total_phases = 7


class ProcessedWebhookFactory(factory.Factory):
    """Factory for creating ProcessedWebhook instances."""

    class Meta:
        model = ProcessedWebhook

    id = factory.LazyFunction(lambda: fake.uuid4())
    event_type = "user.created"
    processed_at = factory.LazyFunction(lambda: datetime.now(UTC))


# =============================================================================
# Factory Fixtures (for easy use in tests)
# =============================================================================


@pytest.fixture
def user_factory():
    """UserFactory for creating test users."""
    return UserFactory


@pytest.fixture
def submission_factory():
    """SubmissionFactory for creating test submissions."""
    return SubmissionFactory


@pytest.fixture
def step_progress_factory():
    """StepProgressFactory for creating test step progress."""
    return StepProgressFactory


@pytest.fixture
def question_attempt_factory():
    """QuestionAttemptFactory for creating test question attempts."""
    return QuestionAttemptFactory


@pytest.fixture
def activity_factory():
    """UserActivityFactory for creating test activities."""
    return UserActivityFactory


@pytest.fixture
def certificate_factory():
    """CertificateFactory for creating test certificates."""
    return CertificateFactory


# =============================================================================
# Existing Fixtures (preserved from original)
# =============================================================================
@pytest.fixture
def faker_instance():
    """Faker instance for generating realistic test data."""
    return fake


@pytest.fixture
def sample_user_id():
    """Generate a realistic user ID."""
    return fake.uuid4()


@pytest.fixture
def sample_github_username():
    """Generate a realistic GitHub username."""
    return fake.user_name()


@pytest.fixture
def sample_github_url(sample_github_username):
    """Generate a realistic GitHub profile URL."""
    return f"https://github.com/{sample_github_username}"


# Phase Requirements Fixtures


@pytest.fixture
def phase_0_requirements():
    """Phase 0 requirements (IT Fundamentals & Cloud Overview)."""
    return {"steps": 15, "questions": 12, "hands_on": 1}


@pytest.fixture
def phase_1_requirements():
    """Phase 1 requirements (Linux, CLI & Version Control)."""
    return {"steps": 36, "questions": 12, "hands_on": 3}


@pytest.fixture
def phase_5_requirements():
    """Phase 5 requirements (DevOps & Containers)."""
    return {"steps": 55, "questions": 12, "hands_on": 4}


@pytest.fixture
def all_phase_ids():
    """All valid phase IDs (0-6)."""
    return [0, 1, 2, 3, 4, 5, 6]


# PhaseProgress Fixtures


@pytest.fixture
def empty_phase_progress():
    """Phase with zero progress."""
    return PhaseProgress(
        phase_id=0,
        steps_completed=0,
        steps_required=15,
        questions_passed=0,
        questions_required=12,
        hands_on_validated_count=0,
        hands_on_required_count=1,
        hands_on_validated=False,
        hands_on_required=True,
    )


@pytest.fixture
def completed_phase_progress():
    """Phase with all requirements completed."""
    return PhaseProgress(
        phase_id=0,
        steps_completed=15,
        steps_required=15,
        questions_passed=12,
        questions_required=12,
        hands_on_validated_count=1,
        hands_on_required_count=1,
        hands_on_validated=True,
        hands_on_required=True,
    )


@pytest.fixture
def partial_phase_progress():
    """Phase with partial progress (only steps completed)."""
    return PhaseProgress(
        phase_id=1,
        steps_completed=36,
        steps_required=36,
        questions_passed=6,
        questions_required=12,
        hands_on_validated_count=0,
        hands_on_required_count=3,
        hands_on_validated=False,
        hands_on_required=True,
    )


@pytest.fixture
def no_hands_on_phase_progress():
    """Phase with no hands-on requirements (hypothetical)."""
    return PhaseProgress(
        phase_id=0,
        steps_completed=15,
        steps_required=15,
        questions_passed=12,
        questions_required=12,
        hands_on_validated_count=0,
        hands_on_required_count=0,
        hands_on_validated=True,
        hands_on_required=False,
    )


@pytest.fixture
def missing_hands_on_phase_progress():
    """Phase with steps and questions done but missing hands-on."""
    return PhaseProgress(
        phase_id=0,
        steps_completed=15,
        steps_required=15,
        questions_passed=12,
        questions_required=12,
        hands_on_validated_count=0,
        hands_on_required_count=1,
        hands_on_validated=False,
        hands_on_required=True,
    )


# UserProgress Fixtures


@pytest.fixture
def empty_user_progress(sample_user_id):
    """User with no progress in any phase."""
    phases = {}
    for phase_id in range(7):
        from services.progress_service import PHASE_REQUIREMENTS

        req = PHASE_REQUIREMENTS[phase_id]
        from services.phase_requirements_service import get_requirements_for_phase

        hands_on_count = len(get_requirements_for_phase(phase_id))
        phases[phase_id] = PhaseProgress(
            phase_id=phase_id,
            steps_completed=0,
            steps_required=req.steps,
            questions_passed=0,
            questions_required=req.questions,
            hands_on_validated_count=0,
            hands_on_required_count=hands_on_count,
            hands_on_validated=hands_on_count == 0,
            hands_on_required=hands_on_count > 0,
        )
    return UserProgress(user_id=sample_user_id, phases=phases)


@pytest.fixture
def completed_user_progress(sample_user_id):
    """User with all phases completed."""
    phases = {}
    for phase_id in range(7):
        from services.progress_service import PHASE_REQUIREMENTS

        req = PHASE_REQUIREMENTS[phase_id]
        from services.phase_requirements_service import get_requirements_for_phase

        hands_on_count = len(get_requirements_for_phase(phase_id))
        phases[phase_id] = PhaseProgress(
            phase_id=phase_id,
            steps_completed=req.steps,
            steps_required=req.steps,
            questions_passed=req.questions,
            questions_required=req.questions,
            hands_on_validated_count=hands_on_count,
            hands_on_required_count=hands_on_count,
            hands_on_validated=True,
            hands_on_required=hands_on_count > 0,
        )
    return UserProgress(user_id=sample_user_id, phases=phases)


@pytest.fixture
def mid_program_user_progress(sample_user_id):
    """User who has completed phase 0 and is working on phase 1."""
    from services.phase_requirements_service import get_requirements_for_phase
    from services.progress_service import PHASE_REQUIREMENTS

    phases = {}

    # Phase 0: completed
    req0 = PHASE_REQUIREMENTS[0]
    hands_on_0 = len(get_requirements_for_phase(0))
    phases[0] = PhaseProgress(
        phase_id=0,
        steps_completed=req0.steps,
        steps_required=req0.steps,
        questions_passed=req0.questions,
        questions_required=req0.questions,
        hands_on_validated_count=hands_on_0,
        hands_on_required_count=hands_on_0,
        hands_on_validated=True,
        hands_on_required=True,
    )

    # Phase 1: partial progress
    req1 = PHASE_REQUIREMENTS[1]
    hands_on_1 = len(get_requirements_for_phase(1))
    phases[1] = PhaseProgress(
        phase_id=1,
        steps_completed=18,
        steps_required=req1.steps,
        questions_passed=6,
        questions_required=req1.questions,
        hands_on_validated_count=1,
        hands_on_required_count=hands_on_1,
        hands_on_validated=False,
        hands_on_required=True,
    )

    # Remaining phases: no progress
    for phase_id in range(2, 7):
        req = PHASE_REQUIREMENTS[phase_id]
        hands_on_count = len(get_requirements_for_phase(phase_id))
        phases[phase_id] = PhaseProgress(
            phase_id=phase_id,
            steps_completed=0,
            steps_required=req.steps,
            questions_passed=0,
            questions_required=req.questions,
            hands_on_validated_count=0,
            hands_on_required_count=hands_on_count,
            hands_on_validated=hands_on_count == 0,
            hands_on_required=hands_on_count > 0,
        )

    return UserProgress(user_id=sample_user_id, phases=phases)


# Submission Fixtures


@pytest.fixture
def validated_submission(sample_user_id, sample_github_username):
    """A validated hands-on submission."""
    return Submission(
        id=1,
        user_id=sample_user_id,
        requirement_id="phase0-github-profile",
        submission_type=SubmissionType.GITHUB_PROFILE,
        phase_id=0,
        submitted_value=f"https://github.com/{sample_github_username}",
        extracted_username=sample_github_username,
        is_validated=True,
    )


@pytest.fixture
def unvalidated_submission(sample_user_id):
    """An unvalidated hands-on submission."""
    return Submission(
        id=2,
        user_id=sample_user_id,
        requirement_id="phase1-profile-readme",
        submission_type=SubmissionType.PROFILE_README,
        phase_id=1,
        submitted_value="https://github.com/invaliduser/invaliduser",
        extracted_username="invaliduser",
        is_validated=False,
    )


@pytest.fixture
def multiple_submissions(sample_user_id, sample_github_username):
    """Multiple submissions across different phases."""
    return [
        Submission(
            id=1,
            user_id=sample_user_id,
            requirement_id="phase0-github-profile",
            submission_type=SubmissionType.GITHUB_PROFILE,
            phase_id=0,
            submitted_value=f"https://github.com/{sample_github_username}",
            extracted_username=sample_github_username,
            is_validated=True,
        ),
        Submission(
            id=2,
            user_id=sample_user_id,
            requirement_id="phase1-profile-readme",
            submission_type=SubmissionType.PROFILE_README,
            phase_id=1,
            submitted_value=f"https://github.com/{sample_github_username}/{sample_github_username}",
            extracted_username=sample_github_username,
            is_validated=True,
        ),
        Submission(
            id=3,
            user_id=sample_user_id,
            requirement_id="phase1-linux-ctfs-fork",
            submission_type=SubmissionType.REPO_FORK,
            phase_id=1,
            submitted_value=f"https://github.com/{sample_github_username}/linux-ctfs",
            extracted_username=sample_github_username,
            is_validated=False,
        ),
    ]


# Parameterized Test Data


@pytest.fixture
def streak_thresholds():
    """Streak badge thresholds for parameterized tests."""
    return [
        (0, []),
        (6, []),
        (7, ["streak_7"]),
        (29, ["streak_7"]),
        (30, ["streak_7", "streak_30"]),
        (99, ["streak_7", "streak_30"]),
        (100, ["streak_7", "streak_30", "streak_100"]),
        (365, ["streak_7", "streak_30", "streak_100"]),
    ]


@pytest.fixture
def valid_topic_ids():
    """Valid topic IDs for testing topic ID parsing."""
    return [
        ("phase0-topic1", 0),
        ("phase1-topic3", 1),
        ("phase2-topic5", 2),
        ("phase3-topic2", 3),
        ("phase4-topic7", 4),
        ("phase5-topic4", 5),
        ("phase6-topic6", 6),
    ]


@pytest.fixture
def valid_question_ids():
    """Valid question IDs for testing question ID parsing."""
    return [
        ("phase0-topic1-q1", 0),
        ("phase1-topic2-q2", 1),
        ("phase2-topic3-q1", 2),
        ("phase3-topic1-q2", 3),
        ("phase4-topic5-q1", 4),
        ("phase5-topic2-q2", 5),
        ("phase6-topic4-q1", 6),
    ]


@pytest.fixture
def invalid_ids():
    """Invalid IDs for testing error handling."""
    return [
        "",
        "invalid",
        "topic1",
        "phase",
        "phase-topic1",
        "phasex-topic1",
        123,
        None,
        [],
    ]


# HandsOnRequirement Fixtures


@pytest.fixture
def sample_hands_on_requirement():
    """Sample hands-on requirement for testing."""
    return HandsOnRequirementData(
        id="test-requirement",
        phase_id=0,
        submission_type=SubmissionType.GITHUB_PROFILE,
        name="Test Requirement",
        description="This is a test requirement",
        example_url="https://github.com/example",
    )
