"""Centralized progress tracking module.

This module provides a single source of truth for:
- Phase requirements (steps, questions, topics) - derived from content JSON
- User progress calculation
- Phase completion status

All progress-related logic (certificates, dashboard, badges) should use this module
to ensure consistency across the application.

CACHING:
- User progress is cached for 60 seconds per user_id
- Cache is per-worker, not distributed (acceptable for read-heavy data)
- Call invalidate_progress_cache(user_id) after progress modifications
"""

import asyncio
import logging
from dataclasses import dataclass
from functools import lru_cache

from sqlalchemy.ext.asyncio import AsyncSession

from core.cache import get_cached_progress, set_cached_progress
from repositories.progress_repository import (
    QuestionAttemptRepository,
    StepProgressRepository,
)
from repositories.submission_repository import SubmissionRepository
from services.hands_on_verification_service import get_requirements_for_phase

logger = logging.getLogger(__name__)


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
        return len(_ensure_requirements_loaded())

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


@lru_cache(maxsize=1)
def _build_phase_requirements() -> dict[int, PhaseRequirements]:
    """Build PHASE_REQUIREMENTS from content JSON files at startup.

    This derives step/question/topic counts from the actual content,
    eliminating the need for hardcoded values that can get out of sync.
    """
    from services.content_service import get_all_phases

    requirements: dict[int, PhaseRequirements] = {}
    phases = get_all_phases()

    for phase in phases:
        total_steps = 0
        total_questions = 0
        for topic in phase.topics:
            total_steps += len(topic.learning_steps)
            total_questions += len(topic.questions)

        requirements[phase.id] = PhaseRequirements(
            phase_id=phase.id,
            name=phase.name,
            topics=len(phase.topics),
            steps=total_steps,
            questions=total_questions,
        )

    logger.info(
        f"Built PHASE_REQUIREMENTS from content: {len(requirements)} phases, "
        f"{sum(r.steps for r in requirements.values())} steps, "
        f"{sum(r.questions for r in requirements.values())} questions"
    )
    return requirements


# Module-level accessor that lazily builds requirements on first access
def _get_phase_requirements() -> dict[int, PhaseRequirements]:
    return _build_phase_requirements()


# For backward compatibility, expose as a property-like accessor
# Code should use get_phase_requirements() or _get_phase_requirements()
PHASE_REQUIREMENTS: dict[int, PhaseRequirements] = {}  # Populated on first access


def _ensure_requirements_loaded() -> dict[int, PhaseRequirements]:
    """Ensure PHASE_REQUIREMENTS is populated and return it."""
    global PHASE_REQUIREMENTS
    if not PHASE_REQUIREMENTS:
        PHASE_REQUIREMENTS.update(_get_phase_requirements())
    return PHASE_REQUIREMENTS


# Computed at module load time after first access
def _get_total_phases() -> int:
    return len(_ensure_requirements_loaded())


def _get_total_topics() -> int:
    return sum(r.topics for r in _ensure_requirements_loaded().values())


def _get_total_steps() -> int:
    return sum(r.steps for r in _ensure_requirements_loaded().values())


def _get_total_questions() -> int:
    return sum(r.questions for r in _ensure_requirements_loaded().values())


def get_phase_requirements(phase_id: int) -> PhaseRequirements | None:
    """Get requirements for a specific phase."""
    return _ensure_requirements_loaded().get(phase_id)


def get_all_phase_ids() -> list[int]:
    """Get all phase IDs in order."""
    return sorted(_ensure_requirements_loaded().keys())


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
    skip_cache: bool = False,
) -> UserProgress:
    """Fetch complete progress data for a user.

    This is the main entry point for getting user progress. It queries:
    - Passed questions per phase
    - Completed steps per phase
    - Validated GitHub submissions per phase

    Args:
        db: Database session
        user_id: User identifier
        skip_cache: If True, bypass cache and fetch fresh data

    Returns a UserProgress object with all phase completion data.

    CACHING: Results are cached for 60 seconds per user_id.
    """
    from services.submissions_service import get_validated_ids_by_phase

    # Check cache first (unless skip_cache is True)
    if not skip_cache:
        cached = get_cached_progress(user_id)
        if cached is not None:
            return cached

    question_repo = QuestionAttemptRepository(db)
    step_repo = StepProgressRepository(db)
    submission_repo = SubmissionRepository(db)

    # Parallelize the 3 independent DB queries for better performance
    question_ids, topic_ids, db_submissions = await asyncio.gather(
        question_repo.get_all_passed_question_ids(user_id),
        step_repo.get_completed_step_topic_ids(user_id),
        submission_repo.get_validated_by_user(user_id),
    )

    # Parse phase numbers from question IDs in service layer
    phase_questions: dict[int, int] = {}
    for question_id in question_ids:
        phase_num = _parse_phase_from_question_id(question_id)
        if phase_num is not None:
            phase_questions[phase_num] = phase_questions.get(phase_num, 0) + 1

    # Parse phase numbers from topic IDs in service layer
    phase_steps: dict[int, int] = {}
    for topic_id in topic_ids:
        phase_num = _parse_phase_from_topic_id(topic_id)
        if phase_num is not None:
            phase_steps[phase_num] = phase_steps.get(phase_num, 0) + 1

    validated_by_phase = get_validated_ids_by_phase(db_submissions)

    phases: dict[int, PhaseProgress] = {}
    for phase_id in get_all_phase_ids():
        requirements = get_phase_requirements(phase_id)
        if not requirements:
            continue
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

    result = UserProgress(user_id=user_id, phases=phases)

    # Cache the result
    set_cached_progress(user_id, result)

    return result


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
