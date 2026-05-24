"""Centralized progress tracking module.

Progress is a derived value, not stored state:

    progress = what the user has done / what the content requires

Data sources:
- Step completions: ``step_progress`` table (canonical)
- Hands-on validations: ``submissions`` table (canonical)
- Curriculum shape: DB-backed via ``content_service`` (synced from YAML
  at deploy time)
"""

import logging

from learn_to_cloud_shared.content_service import get_all_phases
from learn_to_cloud_shared.repositories.progress_repository import (
    StepProgressRepository,
)
from learn_to_cloud_shared.repositories.submission_repository import (
    SubmissionRepository,
)
from learn_to_cloud_shared.schemas import (
    Phase,
    PhaseProgress,
    PhaseProgressData,
    PhaseRequirements,
    Topic,
    TopicProgressData,
    UserProgress,
)
from learn_to_cloud_shared.verification.requirements import RequirementIndex
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)


def _build_phase_requirements(
    phases: tuple[Phase, ...],
) -> dict[int, PhaseRequirements]:
    """Derive per-phase totals (topic count, step count) from loaded phases."""
    requirements: dict[int, PhaseRequirements] = {}
    for phase in phases:
        total_steps = sum(len(topic.learning_steps) for topic in phase.topics)
        requirements[phase.id] = PhaseRequirements(
            phase_id=phase.id,
            name=phase.name,
            topics=len(phase.topics),
            steps=total_steps,
        )
    return requirements


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
    *,
    phases: tuple[Phase, ...] | None = None,
) -> UserProgress:
    """Fetch complete progress data for a user.

    This is the main entry point for getting user progress. It queries:
    - Completed steps per phase (from step_progress table)
    - Validated submissions (from submissions table, filtered to current content)

    Args:
        db: Database session.
        user_id: User identifier.
        phases: Optional pre-loaded phase tree. When provided (e.g. by the
            dashboard service), avoids a redundant curriculum load.

    Returns a UserProgress object with all phase completion data.
    """
    if phases is None:
        phases = await get_all_phases(db)

    phase_requirements = _build_phase_requirements(phases)
    req_index = RequirementIndex.from_phases(phases)

    sub_repo = SubmissionRepository(db)
    validated_req_ids = await sub_repo.get_validated_requirement_ids(user_id)

    step_repo = StepProgressRepository(db)
    all_step_uuids = [
        step.uuid
        for phase in phases
        for topic in phase.topics
        for step in topic.learning_steps
    ]
    completed_step_uuids = await step_repo.get_completed_step_uuids(
        user_id, all_step_uuids
    )

    phase_steps: dict[int, int] = {}
    for phase in phases:
        total_completed = 0
        for topic in phase.topics:
            topic_uuids = {step.uuid for step in topic.learning_steps}
            total_completed += len(completed_step_uuids & topic_uuids)
        phase_steps[phase.id] = total_completed

    phase_progress_map: dict[int, PhaseProgress] = {}
    for phase_id, requirements in phase_requirements.items():
        current_req_ids = {
            req_id for req_id in req_index.requirement_ids_for_phase(phase_id)
        }
        hands_on_validated = len(validated_req_ids & current_req_ids)
        hands_on_required = len(current_req_ids)

        phase_progress_map[phase_id] = _compute_phase_progress(
            phase_id=phase_id,
            steps_completed=phase_steps.get(phase_id, 0),
            steps_required=requirements.steps,
            hands_on_validated=hands_on_validated,
            hands_on_required=hands_on_required,
        )

    return UserProgress(
        user_id=user_id,
        phases=phase_progress_map,
        total_phases=len(phase_requirements),
    )


def compute_topic_progress(
    topic: Topic,
    completed_steps: set[str],
) -> TopicProgressData:
    """Compute progress for a single topic.

    Topic Progress = Steps Completed / Total Steps
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

    Derives required totals and requirement ids from the passed ``phase``
    object so we never re-load the curriculum here.
    """
    step_repo = StepProgressRepository(db)
    all_step_uuids = [
        step.uuid for topic in phase.topics for step in topic.learning_steps
    ]
    completed_step_uuids = await step_repo.get_completed_step_uuids(
        user_id, all_step_uuids
    )

    topic_progress: dict[str, TopicProgressData] = {}
    total_completed = 0
    total_steps = 0

    for topic in phase.topics:
        completed_step_ids = {
            step.id
            for step in topic.learning_steps
            if step.uuid in completed_step_uuids
        }
        tp = compute_topic_progress(topic, completed_step_ids)
        topic_progress[topic.id] = tp
        total_completed += tp.steps_completed
        total_steps += tp.steps_total

    current_req_ids: set[str] = set()
    if phase.hands_on_verification:
        current_req_ids = {r.id for r in phase.hands_on_verification.requirements}
    hands_on_required = len(current_req_ids)

    hands_on_validated = 0
    if hands_on_required > 0:
        sub_repo = SubmissionRepository(db)
        hands_on_validated = await sub_repo.count_validated_for_requirements(
            user_id, current_req_ids
        )

    return _compute_phase_progress(
        phase_id=phase.id,
        steps_completed=total_completed,
        steps_required=total_steps,
        hands_on_validated=hands_on_validated,
        hands_on_required=hands_on_required,
        topic_progress=topic_progress,
    )


def phase_progress_to_data(progress: PhaseProgress) -> PhaseProgressData:
    """Convert PhaseProgress to PhaseProgressData response model."""
    return PhaseProgressData(
        steps_completed=progress.steps_completed,
        steps_required=progress.steps_required,
        hands_on_validated=progress.hands_on_validated,
        hands_on_required=progress.hands_on_required,
        percentage=round(progress.percentage, 1),
        status=progress.status,
    )
