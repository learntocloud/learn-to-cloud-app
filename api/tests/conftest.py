"""Shared test fixtures for the Learn to Cloud test suite.

Provides:
- Faker instance for realistic test data
- Phase requirements fixtures
- PhaseProgress fixtures (empty, completed, partial, no hands-on)
- UserProgress fixtures (empty, completed)
- Submission fixtures (validated, unvalidated)
- Parameterized test data (phase IDs, streak thresholds)
"""

import pytest
from faker import Faker

from models import Submission, SubmissionType
from services.phase_requirements import HandsOnRequirementData
from services.progress import PhaseProgress, UserProgress

# Initialize Faker for realistic data generation
fake = Faker()


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
        from services.progress import PHASE_REQUIREMENTS

        req = PHASE_REQUIREMENTS[phase_id]
        from services.phase_requirements import get_requirements_for_phase

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
        from services.progress import PHASE_REQUIREMENTS

        req = PHASE_REQUIREMENTS[phase_id]
        from services.phase_requirements import get_requirements_for_phase

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
    from services.phase_requirements import get_requirements_for_phase
    from services.progress import PHASE_REQUIREMENTS

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
