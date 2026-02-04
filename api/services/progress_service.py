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

import asyncio
from functools import lru_cache

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from core import get_logger
from core.cache import get_cached_progress, set_cached_progress
from core.wide_event import set_wide_event_fields
from models import User, UserPhaseProgress
from repositories.progress_repository import (
    StepProgressRepository,
    UserPhaseProgressRepository,
)
from repositories.submission_repository import SubmissionRepository
from schemas import (
    PhaseProgress,
    PhaseProgressData,
    PhaseRequirements,
    Topic,
    TopicProgressData,
    UserProgress,
)
from services.content_service import get_all_phases
from services.hands_on_verification_service import get_requirements_for_phase

logger = get_logger(__name__)


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
        phases=len(requirements),
        steps=sum(r.steps for r in requirements.values()),
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


async def fetch_user_progress(
    db: AsyncSession,
    user_id: str,
    skip_cache: bool = False,
) -> UserProgress:
    """Fetch complete progress data for a user.

    This is the main entry point for getting user progress. It queries:
    - Completed steps per phase
    - Validated GitHub submissions per phase

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

    phase_summary = await _get_or_build_phase_summary(db, user_id)

    phases: dict[int, PhaseProgress] = {}
    for phase_id in get_all_phase_ids():
        requirements = get_phase_requirements(phase_id)
        if not requirements:
            continue
        hands_on_requirements = get_requirements_for_phase(phase_id)
        summary = phase_summary.get(phase_id)
        steps_completed = summary.steps_completed if summary else 0
        hands_on_validated_count = summary.hands_on_validated_count if summary else 0

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

    # Add progress context to wide event for observability
    set_wide_event_fields(
        progress_phases_completed=result.phases_completed,
        progress_total_phases=result.total_phases,
        progress_percentage=round(result.overall_percentage, 1),
        progress_is_complete=result.is_program_complete,
    )

    return result


async def _get_or_build_phase_summary(
    db: AsyncSession,
    user_id: str,
) -> dict[int, "UserPhaseProgress"]:
    summary_repo = UserPhaseProgressRepository(db)
    rows = await summary_repo.get_by_user(user_id)
    if not rows:
        await _build_summary_from_history(db, user_id, summary_repo)
        rows = await summary_repo.get_by_user(user_id)
    return {row.phase_id: row for row in rows}


async def _build_summary_from_history(
    db: AsyncSession,
    user_id: str,
    summary_repo: UserPhaseProgressRepository,
) -> None:
    await rebuild_user_phase_summary(db, user_id, summary_repo=summary_repo)


async def rebuild_user_phase_summary(
    db: AsyncSession,
    user_id: str,
    *,
    summary_repo: UserPhaseProgressRepository | None = None,
) -> int:
    step_repo = StepProgressRepository(db)
    submission_repo = SubmissionRepository(db)
    summary_repo = summary_repo or UserPhaseProgressRepository(db)

    # Parallelize the 3 independent DB queries for better performance
    phase_steps, validated_counts = await asyncio.gather(
        step_repo.get_step_counts_by_phase(user_id),
        submission_repo.get_validated_counts_by_phase(user_id),
    )

    updated = 0
    for phase_id in get_all_phase_ids():
        steps_completed = phase_steps.get(phase_id, 0)
        validated_count = validated_counts.get(phase_id, 0)
        await summary_repo.upsert_counts(
            user_id=user_id,
            phase_id=phase_id,
            steps_completed=steps_completed,
            hands_on_validated_count=validated_count,
        )
        updated += 1

    return updated


async def rebuild_all_phase_summaries(
    db: AsyncSession, *, user_ids: list[str] | None = None
) -> int:
    if user_ids is None:
        result = await db.execute(select(User.id))
        user_ids = [row[0] for row in result.all()]

    total = 0
    for user_id in user_ids:
        total += await rebuild_user_phase_summary(db, user_id)

    return total


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
    completed_steps: set[int],
) -> TopicProgressData:
    """Compute progress for a single topic.

    Topic Progress = Steps Completed / Total Steps

    Args:
        topic: The topic content definition
        completed_steps: Set of completed step order numbers
    Returns:
        TopicProgressData with completion status and percentages
    """
    steps_completed = len(completed_steps)
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


def is_topic_complete(
    topic: Topic,
    completed_steps: set[int],
) -> bool:
    """Check if a topic is fully completed.

    A topic is complete when all learning steps are done.

    Args:
        topic: The topic content definition
        completed_steps: Set of completed step order numbers
    Returns:
        True if topic is complete, False otherwise
    """
    return len(completed_steps) >= len(topic.learning_steps)


def is_phase_locked(
    phase_id: int,
    user_progress: UserProgress | None,
    is_admin: bool,
) -> bool:
    """Determine if a phase is locked for the user.

    Locking rules:
    - Phase 0: Always unlocked
    - Phases 1+: Previous phase must be complete
    - Admin users: Bypass all locks

    Args:
        phase_id: The phase ID to check
        user_progress: User's progress data (None for unauthenticated users)
        is_admin: Whether the user has admin privileges

    Returns:
        True if the phase is locked, False if unlocked
    """
    if is_admin:
        return False
    if phase_id == 0:
        return False
    if user_progress is None:
        return True
    prev_progress = user_progress.phases.get(phase_id - 1)
    return not (prev_progress and prev_progress.is_complete)


def is_topic_locked(
    topic_order: int,
    phase_is_locked: bool,
    prev_topic_complete: bool,
    is_admin: bool,
) -> bool:
    """Determine if a topic is locked for the user.

    Locking rules:
    - First topic (order=1): Unlocked if phase is unlocked
    - Subsequent topics: Previous topic must be complete
    - Admin users: Bypass all locks

    Args:
        topic_order: The topic's order within the phase (1-indexed)
        phase_is_locked: Whether the containing phase is locked
        prev_topic_complete: Whether the previous topic is complete
        is_admin: Whether the user has admin privileges

    Returns:
        True if the topic is locked, False if unlocked
    """
    if is_admin:
        return False
    if phase_is_locked:
        return True
    if topic_order == 1:
        return False
    return not prev_topic_complete


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
