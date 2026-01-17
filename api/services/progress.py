"""Centralized progress tracking module.

This module provides a single source of truth for:
- Phase requirements (steps, questions, topics)
- User progress calculation
- Phase completion status

All progress-related logic (certificates, dashboard, badges) should use this module
to ensure consistency across the application.
"""

from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession

from repositories.progress import QuestionAttemptRepository, StepProgressRepository
from repositories.submission import SubmissionRepository
from services.hands_on_verification import get_requirements_for_phase


@dataclass
class PhaseRequirements:
    """Requirements to complete a phase."""

    phase_id: int
    name: str
    topics: int
    steps: int
    questions: int

    @property
    def questions_per_topic(self) -> int:
        """Each topic has 2 questions."""
        return 2


@dataclass
class PhaseProgress:
    """User's progress for a single phase."""

    phase_id: int
    steps_completed: int
    steps_required: int
    questions_passed: int
    questions_required: int
    hands_on_validated_count: int
    hands_on_required_count: int

    hands_on_validated: bool
    hands_on_required: bool

    @property
    def is_complete(self) -> bool:
        """Phase is complete when all requirements are met."""
        return (
            self.steps_completed >= self.steps_required
            and self.questions_passed >= self.questions_required
            and self.hands_on_validated
        )

    @property
    def hands_on_percentage(self) -> float:
        """Percentage of hands-on requirements validated for this phase."""
        if self.hands_on_required_count == 0:
            return 100.0
        return min(
            100.0, (self.hands_on_validated_count / self.hands_on_required_count) * 100
        )

    @property
    def overall_percentage(self) -> float:
        """Phase completion percentage (steps + questions + hands-on).

        Skill source of truth:
          (Steps + Questions + Hands-on) / (Total Steps + Questions + Hands-on)
        """
        total = (
            self.steps_required + self.questions_required + self.hands_on_required_count
        )
        if total == 0:
            return 0.0

        completed = (
            min(self.steps_completed, self.steps_required)
            + min(self.questions_passed, self.questions_required)
            + min(self.hands_on_validated_count, self.hands_on_required_count)
        )
        return (completed / total) * 100

    @property
    def step_percentage(self) -> float:
        """Percentage of steps completed."""
        if self.steps_required == 0:
            return 100.0
        return min(100.0, (self.steps_completed / self.steps_required) * 100)

    @property
    def question_percentage(self) -> float:
        """Percentage of questions passed."""
        if self.questions_required == 0:
            return 100.0
        return min(100.0, (self.questions_passed / self.questions_required) * 100)


@dataclass
class UserProgress:
    """Complete progress summary for a user."""

    user_id: str
    phases: dict[int, PhaseProgress]

    @property
    def phases_completed(self) -> int:
        """Count of fully completed phases."""
        return sum(1 for p in self.phases.values() if p.is_complete)

    @property
    def total_phases(self) -> int:
        """Total number of phases."""
        return len(PHASE_REQUIREMENTS)

    @property
    def current_phase(self) -> int:
        """First incomplete phase, or last phase if all done."""
        for phase_id in sorted(self.phases.keys()):
            if not self.phases[phase_id].is_complete:
                return phase_id
        return max(self.phases.keys()) if self.phases else 0

    @property
    def is_program_complete(self) -> bool:
        """True if all phases are completed."""
        return self.phases_completed == self.total_phases

    @property
    def overall_percentage(self) -> float:
        """Overall completion percentage across all phases."""
        if not self.phases:
            return 0.0

        total_steps = sum(p.steps_required for p in self.phases.values())
        total_questions = sum(p.questions_required for p in self.phases.values())
        total_hands_on = sum(p.hands_on_required_count for p in self.phases.values())
        completed_steps = sum(p.steps_completed for p in self.phases.values())
        passed_questions = sum(p.questions_passed for p in self.phases.values())
        completed_hands_on = sum(
            p.hands_on_validated_count for p in self.phases.values()
        )

        if total_steps + total_questions + total_hands_on == 0:
            return 0.0

        total = total_steps + total_questions + total_hands_on
        completed = (
            min(completed_steps, total_steps)
            + min(passed_questions, total_questions)
            + min(completed_hands_on, total_hands_on)
        )
        return (completed / total) * 100


PHASE_REQUIREMENTS: dict[int, PhaseRequirements] = {
    0: PhaseRequirements(
        phase_id=0,
        name="IT Fundamentals & Cloud Overview",
        topics=6,
        steps=15,
        questions=12,
    ),
    1: PhaseRequirements(
        phase_id=1,
        name="Linux, CLI & Version Control",
        topics=6,
        steps=36,
        questions=12,
    ),
    2: PhaseRequirements(
        phase_id=2,
        name="Programming & APIs",
        topics=6,
        steps=30,
        questions=12,
    ),
    3: PhaseRequirements(
        phase_id=3,
        name="AI & Productivity",
        topics=4,
        steps=31,
        questions=8,
    ),
    4: PhaseRequirements(
        phase_id=4,
        name="Cloud Deployment",
        topics=9,
        steps=51,
        questions=18,
    ),
    5: PhaseRequirements(
        phase_id=5,
        name="DevOps & Containers",
        topics=6,
        steps=55,
        questions=12,
    ),
    6: PhaseRequirements(
        phase_id=6,
        name="Cloud Security",
        topics=6,
        steps=64,
        questions=12,
    ),
}

TOTAL_PHASES = len(PHASE_REQUIREMENTS)
TOTAL_TOPICS = sum(r.topics for r in PHASE_REQUIREMENTS.values())
TOTAL_STEPS = sum(r.steps for r in PHASE_REQUIREMENTS.values())
TOTAL_QUESTIONS = sum(r.questions for r in PHASE_REQUIREMENTS.values())


def get_phase_requirements(phase_id: int) -> PhaseRequirements | None:
    """Get requirements for a specific phase."""
    return PHASE_REQUIREMENTS.get(phase_id)


def get_all_phase_ids() -> list[int]:
    """Get all phase IDs in order."""
    return sorted(PHASE_REQUIREMENTS.keys())


def _parse_phase_from_topic_id(topic_id: str) -> int | None:
    """Extract phase number from topic_id format (phase{N}-topic{M}).

    Args:
        topic_id: Topic ID in format "phase{N}-topic{M}"

    Returns:
        Phase number or None if parsing fails
    """
    if not isinstance(topic_id, str) or not topic_id.startswith("phase"):
        return None
    try:
        return int(topic_id.split("-")[0].replace("phase", ""))
    except (ValueError, IndexError):
        return None


def _parse_phase_from_question_id(question_id: str) -> int | None:
    """Extract phase number from question_id format (phase{N}-topic{M}-q{X}).

    Args:
        question_id: Question ID in format "phase{N}-topic{M}-q{X}"

    Returns:
        Phase number or None if parsing fails
    """
    if not isinstance(question_id, str) or not question_id.startswith("phase"):
        return None
    try:
        return int(question_id.split("-")[0].replace("phase", ""))
    except (ValueError, IndexError):
        return None


async def fetch_user_progress(
    db: AsyncSession,
    user_id: str,
) -> UserProgress:
    """Fetch complete progress data for a user.

    This is the main entry point for getting user progress. It queries:
    - Passed questions per phase
    - Completed steps per phase
    - Validated GitHub submissions per phase

    Returns a UserProgress object with all phase completion data.
    """
    from services.submissions import get_validated_ids_by_phase

    question_repo = QuestionAttemptRepository(db)
    step_repo = StepProgressRepository(db)
    submission_repo = SubmissionRepository(db)

    # Get raw question IDs and parse phase numbers in service layer
    question_ids = await question_repo.get_all_passed_question_ids(user_id)
    phase_questions: dict[int, int] = {}
    for question_id in question_ids:
        phase_num = _parse_phase_from_question_id(question_id)
        if phase_num is not None:
            phase_questions[phase_num] = phase_questions.get(phase_num, 0) + 1

    # Get raw topic IDs and parse phase numbers in service layer
    topic_ids = await step_repo.get_completed_step_topic_ids(user_id)
    phase_steps: dict[int, int] = {}
    for topic_id in topic_ids:
        phase_num = _parse_phase_from_topic_id(topic_id)
        if phase_num is not None:
            phase_steps[phase_num] = phase_steps.get(phase_num, 0) + 1

    db_submissions = await submission_repo.get_validated_by_user(user_id)
    validated_by_phase = get_validated_ids_by_phase(db_submissions)

    phases: dict[int, PhaseProgress] = {}
    for phase_id, requirements in PHASE_REQUIREMENTS.items():
        hands_on_requirements = get_requirements_for_phase(phase_id)
        required_ids = {r.id for r in hands_on_requirements}
        validated_ids = validated_by_phase.get(phase_id, set())
        hands_on_required_count = len(required_ids)
        hands_on_validated_count = len(required_ids.intersection(validated_ids))
        has_hands_on_requirements = hands_on_required_count > 0
        hands_on_validated = (
            (hands_on_validated_count >= hands_on_required_count)
            if has_hands_on_requirements
            else True
        )

        phases[phase_id] = PhaseProgress(
            phase_id=phase_id,
            steps_completed=phase_steps.get(phase_id, 0),
            steps_required=requirements.steps,
            questions_passed=phase_questions.get(phase_id, 0),
            questions_required=requirements.questions,
            hands_on_validated_count=hands_on_validated_count,
            hands_on_required_count=hands_on_required_count,
            hands_on_validated=hands_on_validated,
            hands_on_required=has_hands_on_requirements,
        )

    return UserProgress(user_id=user_id, phases=phases)


def get_phase_completion_counts(
    progress: UserProgress,
) -> dict[int, tuple[int, int, bool]]:
    """Convert UserProgress to the format expected by badge computation.

    Returns:
        Dict mapping phase_id -> (completed_steps, passed_questions, hands_on_validated)
    """
    return {
        phase_id: (
            phase.steps_completed,
            phase.questions_passed,
            phase.hands_on_validated,
        )
        for phase_id, phase in progress.phases.items()
    }
