"""Centralized progress tracking module.

Progress is a derived value, not stored state:

    progress = what the user has done ÷ what the content requires

Data sources:
- Step completions: ``step_progress`` table (canonical)
- Hands-on validations: ``submissions`` table (canonical)
- Requirements: Content YAML (cached at startup)
"""

import logging
from functools import lru_cache

from sqlalchemy.ext.asyncio import AsyncSession

from repositories.progress_repository import StepProgressRepository
from repositories.submission_repository import SubmissionRepository
from schemas import (
    Phase,
    PhaseProgress,
    PhaseProgressData,
    PhaseRequirements,
    Topic,
    TopicProgressData,
    UserProgress,
)
from services.content_service import get_all_phases
from services.verification.requirements import get_requirements_for_phase

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


def _get_requirement_ids_by_phase() -> dict[int, set[str]]:
    """Get current content requirement IDs grouped by phase."""
    result: dict[int, set[str]] = {}
    for phase_id in get_all_phase_ids():
        requirements = get_requirements_for_phase(phase_id)
        result[phase_id] = {r.id for r in requirements}
    return result


def _compute_phase_progress(
    phase_id: int,
    steps_completed: int,
    steps_required: int,
    hands_on_validated: int,
    hands_on_required: int,
    topic_progress: dict[str, TopicProgressData] | None = None,
) -> PhaseProgress:
    """Core progress computation shared by dashboard and detail views."""
    return PhaseProgress(
        phase_id=phase_id,
        steps_completed=steps_completed,
        steps_required=steps_required,
        hands_on_validated=hands_on_validated,
        hands_on_required=hands_on_required,
        topic_progress=topic_progress,
    )


async def fetch_user_progress(
    db: AsyncSession,
    user_id: int,
) -> UserProgress:
    """Fetch complete progress data for a user.

    This is the main entry point for getting user progress. It queries:
    - Completed steps per phase (from step_progress table)
    - Validated submissions (from submissions table, filtered to current content)

    Args:
        db: Database session
        user_id: User identifier

    Returns a UserProgress object with all phase completion data.
    """

    phases = get_all_phases()

    # Query validated requirement IDs from submissions (source of truth)
    sub_repo = SubmissionRepository(db)
    validated_req_ids = await sub_repo.get_validated_requirement_ids(user_id)

    # Get current content requirement IDs per phase
    req_ids_by_phase = _get_requirement_ids_by_phase()

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

    phase_progress_map: dict[int, PhaseProgress] = {}
    for phase_id in get_all_phase_ids():
        requirements = get_phase_requirements(phase_id)
        if not requirements:
            continue

        current_req_ids = req_ids_by_phase.get(phase_id, set())
        hands_on_validated = len(validated_req_ids & current_req_ids)
        hands_on_required = len(current_req_ids)

        phase_progress_map[phase_id] = _compute_phase_progress(
            phase_id=phase_id,
            steps_completed=phase_steps.get(phase_id, 0),
            steps_required=requirements.steps,
            hands_on_validated=hands_on_validated,
            hands_on_required=hands_on_required,
        )

    all_phase_ids = get_all_phase_ids()
    result = UserProgress(
        user_id=user_id, phases=phase_progress_map, total_phases=len(all_phase_ids)
    )

    return result


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

    if steps_total == 0:
        percentage = 100.0
        status = "completed"
    else:
        percentage = (steps_completed / steps_total) * 100
        if steps_completed >= steps_total:
            status = "completed"
        elif steps_completed > 0:
            status = "in_progress"
        else:
            status = "not_started"

    return TopicProgressData(
        steps_completed=steps_completed,
        steps_total=steps_total,
        percentage=round(percentage, 1),
        status=status,
    )


async def fetch_phase_progress(
    db: AsyncSession,
    user_id: int,
    phase: Phase,
) -> PhaseProgress:
    """Compute progress for a single phase with per-topic breakdown.

    Used by the phase detail page. Same computation as fetch_user_progress
    but scoped to one phase and includes topic-level detail.
    """
    step_repo = StepProgressRepository(db)
    topic_ids = [t.id for t in phase.topics]
    completed_by_topic = await step_repo.get_completed_for_topics(user_id, topic_ids)

    topic_progress: dict[str, TopicProgressData] = {}
    total_completed = 0
    total_steps = 0

    for topic in phase.topics:
        completed_steps = completed_by_topic.get(topic.id, set())
        tp = compute_topic_progress(topic, completed_steps)
        topic_progress[topic.id] = tp
        total_completed += tp.steps_completed
        total_steps += tp.steps_total

    # Count validated submissions from source of truth, filtered to current content
    hands_on_requirements = get_requirements_for_phase(phase.id)
    current_req_ids = {r.id for r in hands_on_requirements}
    hands_on_required = len(current_req_ids)

    hands_on_validated = 0
    if hands_on_required > 0:
        sub_repo = SubmissionRepository(db)
        hands_on_validated = await sub_repo.count_validated_for_requirements(
            user_id, current_req_ids
        )

    requirements = get_phase_requirements(phase.id)
    steps_required = requirements.steps if requirements else total_steps

    result = _compute_phase_progress(
        phase_id=phase.id,
        steps_completed=total_completed,
        steps_required=steps_required,
        hands_on_validated=hands_on_validated,
        hands_on_required=hands_on_required,
        topic_progress=topic_progress,
    )

    return result


def phase_progress_to_data(progress: PhaseProgress) -> PhaseProgressData:
    """Convert PhaseProgress to PhaseProgressData response model.

    Args:
        progress: The phase progress data

    Returns:
        PhaseProgressData suitable for API responses
    """
    return PhaseProgressData(
        steps_completed=progress.steps_completed,
        steps_required=progress.steps_required,
        hands_on_validated=progress.hands_on_validated,
        hands_on_required=progress.hands_on_required,
        percentage=round(progress.percentage, 1),
        status=progress.status,
    )
