"""Centralized progress tracking module.

Progress is a derived value, not stored state:

    progress = what the user has done / what the content requires

Data sources:
- Step completions: ``step_progress`` table (canonical)
- Hands-on validations: ``submissions`` table (canonical)
- Curriculum shape: packaged catalog via ``content_service`` (in-memory,
  no DB reads)
"""

import logging
from collections import defaultdict
from uuid import UUID

from learn_to_cloud_shared.content_catalog import get_curriculum_catalog
from learn_to_cloud_shared.content_service import (
    get_curriculum_overview,
    get_required_step_counts_by_phase,
)
from learn_to_cloud_shared.repositories.progress_repository import (
    StepProgressRepository,
)
from learn_to_cloud_shared.repositories.submission_repository import (
    SubmissionRepository,
)
from learn_to_cloud_shared.requirements import load_requirement_index
from learn_to_cloud_shared.schemas import (
    Phase,
    PhaseOverview,
    PhaseProgress,
    PhaseProgressData,
    Topic,
    TopicProgressData,
    UserProgress,
)
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)


def _compute_phase_progress(
    phase_id: int,
    steps_completed: int,
    steps_required: int,
    hands_on_validated: int,
    hands_on_required: int,
    topic_progress: dict[UUID, TopicProgressData] | None = None,
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
    phase_overview: tuple[PhaseOverview, ...] | None = None,
) -> UserProgress:
    """Fetch complete progress data for a user, via two learner-state queries.

    Reads only ``step_progress``/``submissions`` UUIDs for this user (no
    curriculum-table joins), then groups them by phase order in Python
    using the packaged catalog's ``phase_order_by_step_uuid`` /
    ``phase_order_by_requirement_uuid`` maps. A stale/retired UUID (not
    in the catalog) is simply absent from those maps and drops out.

    Args:
        db: Database session.
        user_id: User identifier.
        phase_overview: Optional pre-loaded phase overview (e.g. by the
            dashboard service), to avoid a redundant lookup.

    Returns a UserProgress object with all phase completion data.
    """
    if phase_overview is None:
        phase_overview = get_curriculum_overview()

    req_index = load_requirement_index()
    required_steps_by_phase = get_required_step_counts_by_phase()
    catalog = get_curriculum_catalog()

    sub_repo = SubmissionRepository(db)
    validated_req_uuids = await sub_repo.get_validated_requirement_uuids(user_id)
    validated_by_phase: dict[int, int] = defaultdict(int)
    for req_uuid in validated_req_uuids:
        phase_order = catalog.phase_order_by_requirement_uuid.get(req_uuid)
        if phase_order is not None:
            validated_by_phase[phase_order] += 1

    step_repo = StepProgressRepository(db)
    completed_step_uuids = await step_repo.get_completed_step_uuids(
        user_id, catalog.active_step_uuids
    )
    completed_steps_by_phase: dict[int, int] = defaultdict(int)
    for step_uuid in completed_step_uuids:
        phase_order = catalog.phase_order_by_step_uuid.get(step_uuid)
        if phase_order is not None:
            completed_steps_by_phase[phase_order] += 1

    phase_progress_map: dict[int, PhaseProgress] = {}
    for phase in phase_overview:
        phase_progress_map[phase.order] = _compute_phase_progress(
            phase_id=phase.order,
            steps_completed=completed_steps_by_phase.get(phase.order, 0),
            steps_required=required_steps_by_phase.get(phase.order, 0),
            hands_on_validated=validated_by_phase.get(phase.order, 0),
            hands_on_required=len(req_index.requirements_for_phase(phase.order)),
        )

    return UserProgress(
        user_id=user_id,
        phases=phase_progress_map,
        total_phases=len(phase_overview),
    )


def compute_topic_progress(
    topic: Topic,
    completed_steps: set[str],
) -> TopicProgressData:
    """Compute progress for a single topic.

    Topic Progress = Steps Completed / Total Steps
    """
    valid_step_slugs = {step.slug for step in topic.learning_steps}
    steps_completed = len(completed_steps & valid_step_slugs)
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

    topic_progress: dict[UUID, TopicProgressData] = {}
    total_completed = 0
    total_steps = 0

    for topic in phase.topics:
        completed_step_slugs = {
            step.slug
            for step in topic.learning_steps
            if step.uuid in completed_step_uuids
        }
        tp = compute_topic_progress(topic, completed_step_slugs)
        topic_progress[topic.uuid] = tp
        total_completed += tp.steps_completed
        total_steps += tp.steps_total

    current_req_uuids: set[UUID] = set()
    if phase.hands_on_verification:
        current_req_uuids = {r.uuid for r in phase.hands_on_verification.requirements}
    hands_on_required = len(current_req_uuids)

    hands_on_validated = 0
    if hands_on_required > 0:
        sub_repo = SubmissionRepository(db)
        hands_on_validated = await sub_repo.count_validated_for_requirements(
            user_id, current_req_uuids
        )

    return _compute_phase_progress(
        phase_id=phase.order,
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
