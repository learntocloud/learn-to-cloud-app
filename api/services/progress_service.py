"""Centralized progress tracking module.

This module provides a single source of truth for:
- Phase requirements (steps, topics) - derived from content JSON
- User progress calculation
- Phase completion status

All progress-related logic (certificates, dashboard, badges) should use this module
to ensure consistency across the application.

CACHING:
- User progress is cached for 60 seconds per user_id
- Cache is per-worker, not distributed (acceptable for read-heavy data)
- Call invalidate_progress_cache(user_id) after progress modifications
"""

import logging
from functools import lru_cache

from sqlalchemy.ext.asyncio import AsyncSession

from core.cache import (
    get_cached_phase_detail,
    get_cached_progress,
    set_cached_phase_detail,
    set_cached_progress,
)
from repositories.progress_denormalized_repository import UserPhaseProgressRepository
from repositories.progress_repository import StepProgressRepository
from schemas import (
    Phase,
    PhaseDetailProgress,
    PhaseProgress,
    PhaseProgressData,
    PhaseRequirements,
    Topic,
    TopicProgressData,
    UserProgress,
)
from services.content_service import get_all_phases
from services.phase_requirements_service import get_requirements_for_phase

logger = logging.getLogger(__name__)


@lru_cache(maxsize=1)
def _build_phase_requirements() -> dict[int, PhaseRequirements]:
    """Build PHASE_REQUIREMENTS from content JSON files at startup.

    This derives step/topic counts from the actual content,
    eliminating the need for hardcoded values that can get out of sync.
    """
    requirements: dict[int, PhaseRequirements] = {}
    phases = get_all_phases()

    for phase in phases:
        total_steps = 0
        for topic in phase.topics:
            total_steps += len(topic.learning_steps)

        requirements[phase.id] = PhaseRequirements(
            phase_id=phase.id,
            name=phase.name,
            topics=len(phase.topics),
            steps=total_steps,
        )

    logger.info(
        "phase_requirements.built",
        extra={
            "phases": len(requirements),
            "steps": sum(r.steps for r in requirements.values()),
        },
    )
    return requirements


def get_phase_requirements(phase_id: int) -> PhaseRequirements | None:
    """Get requirements for a specific phase."""
    return _build_phase_requirements().get(phase_id)


def get_all_phase_ids() -> list[int]:
    """Get all phase IDs in order."""
    return sorted(_build_phase_requirements().keys())


async def fetch_user_progress(
    db: AsyncSession,
    user_id: int,
    skip_cache: bool = False,
) -> UserProgress:
    """Fetch complete progress data for a user.

    This is the main entry point for getting user progress. It queries:
    - Completed steps per phase (from step_progress table)
    - Validated submissions per phase (from submissions table)

    Args:
        db: Database session
        user_id: User identifier
        skip_cache: If True, bypass cache and fetch fresh data

    Returns a UserProgress object with all phase completion data.

    CACHING: Results are cached for 60 seconds per user_id.
    """
    if not skip_cache:
        cached = get_cached_progress(user_id)
        if cached is not None:
            return cached

    phases = get_all_phases()

    progress_repo = UserPhaseProgressRepository(db)
    denormalized = await progress_repo.get_by_user(user_id)

    validated_counts = {
        pid: row.validated_submissions for pid, row in denormalized.items()
    }

    # Canonical step completion: filter persisted completions by currently-defined
    # step ids so content edits (add/remove/reorder) cannot inflate progress.
    step_repo = StepProgressRepository(db)
    all_topic_ids = [topic.id for phase in phases for topic in phase.topics]
    completed_by_topic = await step_repo.get_completed_for_topics(
        user_id, all_topic_ids
    )

    phase_steps: dict[int, int] = {}
    for phase in phases:
        total_completed = 0
        for topic in phase.topics:
            valid_step_ids = {step.id for step in topic.learning_steps}
            completed = completed_by_topic.get(topic.id, set())
            total_completed += len(completed & valid_step_ids)
        phase_steps[phase.id] = total_completed

    for phase_id, canonical_count in phase_steps.items():
        denorm_row = denormalized.get(phase_id)
        if denorm_row is not None and denorm_row.completed_steps != canonical_count:
            await progress_repo.recalculate_steps_for_phase(
                user_id, phase_id, canonical_count
            )

    phases: dict[int, PhaseProgress] = {}
    for phase_id in get_all_phase_ids():
        requirements = get_phase_requirements(phase_id)
        if not requirements:
            continue
        hands_on_requirements = get_requirements_for_phase(phase_id)
        steps_completed = phase_steps.get(phase_id, 0)
        hands_on_validated_count = validated_counts.get(phase_id, 0)

        required_ids = {r.id for r in hands_on_requirements}
        hands_on_required_count = len(required_ids)
        has_hands_on_requirements = hands_on_required_count > 0
        hands_on_validated = (
            (hands_on_validated_count >= hands_on_required_count)
            if has_hands_on_requirements
            else True
        )

        phases[phase_id] = PhaseProgress(
            phase_id=phase_id,
            steps_completed=steps_completed,
            steps_required=requirements.steps,
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
) -> dict[int, tuple[int, bool]]:
    """Convert UserProgress to the format expected by badge computation.

    Returns:
        Dict mapping phase_id -> (completed_steps, hands_on_validated)
    """
    return {
        phase_id: (phase.steps_completed, phase.hands_on_validated)
        for phase_id, phase in progress.phases.items()
    }


def compute_topic_progress(
    topic: Topic,
    completed_steps: set[str],
) -> TopicProgressData:
    """Compute progress for a single topic.

    Topic Progress = Steps Completed / Total Steps

    Args:
        topic: The topic content definition
        completed_steps: Set of completed step IDs
    Returns:
        TopicProgressData with completion status and percentages
    """
    valid_step_ids = {step.id for step in topic.learning_steps}
    steps_completed = len(completed_steps & valid_step_ids)
    steps_total = len(topic.learning_steps)
    total = steps_total
    completed = steps_completed

    if total == 0:
        percentage = 100.0
        status = "completed"
    else:
        percentage = (completed / total) * 100
        if steps_completed >= steps_total:
            status = "completed"
        elif completed > 0:
            status = "in_progress"
        else:
            status = "not_started"

    return TopicProgressData(
        steps_completed=steps_completed,
        steps_total=steps_total,
        percentage=round(percentage, 1),
        status=status,
    )


async def get_phase_detail_progress(
    db: AsyncSession,
    user_id: int,
    phase: Phase,
) -> PhaseDetailProgress:
    """Compute per-topic and overall progress for the phase detail page.

    Uses write-through cache: updated on step complete/uncomplete,
    falls back to DB on cache miss.
    """
    completed_by_topic = get_cached_phase_detail(user_id, phase.id)
    if completed_by_topic is None:
        step_repo = StepProgressRepository(db)
        topic_ids = [t.id for t in phase.topics]
        completed_by_topic = await step_repo.get_completed_for_topics(
            user_id, topic_ids
        )
        set_cached_phase_detail(user_id, phase.id, completed_by_topic)

    topic_progress: dict[str, TopicProgressData] = {}
    total_completed = 0
    total_steps = 0

    for topic in phase.topics:
        completed_steps = completed_by_topic.get(topic.id, set())
        tp = compute_topic_progress(topic, completed_steps)
        topic_progress[topic.id] = tp
        total_completed += tp.steps_completed
        total_steps += tp.steps_total

    percentage = round((total_completed / total_steps) * 100) if total_steps > 0 else 0

    return PhaseDetailProgress(
        topic_progress=topic_progress,
        steps_completed=total_completed,
        steps_total=total_steps,
        percentage=percentage,
    )


def phase_progress_to_data(progress: PhaseProgress) -> PhaseProgressData:
    """Convert PhaseProgress to PhaseProgressData response model.

    Determines the status string based on completion state.

    Args:
        progress: The phase progress data

    Returns:
        PhaseProgressData suitable for API responses
    """
    if progress.is_complete:
        status = "completed"
    elif progress.steps_completed > 0 or progress.hands_on_validated_count > 0:
        status = "in_progress"
    else:
        status = "not_started"

    return PhaseProgressData(
        steps_completed=progress.steps_completed,
        steps_required=progress.steps_required,
        hands_on_validated=progress.hands_on_validated_count,
        hands_on_required=progress.hands_on_required_count,
        percentage=round(progress.overall_percentage, 1),
        status=status,
    )
