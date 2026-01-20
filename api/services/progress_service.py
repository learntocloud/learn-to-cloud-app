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
from functools import lru_cache

from sqlalchemy.ext.asyncio import AsyncSession

from core import get_logger
from core.cache import get_cached_progress, set_cached_progress
from repositories.progress_repository import (
    QuestionAttemptRepository,
    StepProgressRepository,
)
from repositories.submission_repository import SubmissionRepository
from schemas import PhaseProgress, PhaseRequirements, UserProgress
from services.content_service import get_all_phases
from services.hands_on_verification_service import get_requirements_for_phase

logger = get_logger(__name__)


@lru_cache(maxsize=1)
def _build_phase_requirements() -> dict[int, PhaseRequirements]:
    """Build PHASE_REQUIREMENTS from content JSON files at startup.

    This derives step/question/topic counts from the actual content,
    eliminating the need for hardcoded values that can get out of sync.
    """
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


def get_phase_requirements(phase_id: int) -> PhaseRequirements | None:
    """Get requirements for a specific phase."""
    return _build_phase_requirements().get(phase_id)


def get_all_phase_ids() -> list[int]:
    """Get all phase IDs in order."""
    return sorted(_build_phase_requirements().keys())


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

    # Parse phase numbers from question IDs
    phase_questions: dict[int, int] = {}
    for question_id in question_ids:
        phase_num = _parse_phase_from_question_id(question_id)
        if phase_num is not None:
            phase_questions[phase_num] = phase_questions.get(phase_num, 0) + 1

    # Parse phase numbers from topic IDs
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

    all_phase_ids = get_all_phase_ids()
    result = UserProgress(
        user_id=user_id, phases=phases, total_phases=len(all_phase_ids)
    )
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
