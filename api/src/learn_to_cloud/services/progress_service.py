"""Centralized progress tracking module.

Progress is a derived value, not stored state, and is now two separate
measures rather than one blended percentage:

    learning_progress = current catalog steps checked / current catalog steps
    verification_progress = current catalog requirements succeeded / current
        catalog requirements (only a ``succeeded`` attempt counts)

A phase is complete only when both measures are complete (see
``PhaseProgress.is_complete``); a phase with zero requirements is
verification-complete by definition, and a phase with zero steps is
learning-complete by definition.

Step completion and verification state come from their authoritative tables.
Curriculum shape comes from the packaged in-memory catalog.
"""

import logging
from collections import defaultdict
from collections.abc import Iterable, Mapping
from uuid import UUID

from learn_to_cloud_shared.content_catalog import get_curriculum_catalog
from learn_to_cloud_shared.content_service import (
    get_curriculum_overview,
    get_required_step_counts_by_phase,
)
from learn_to_cloud_shared.progress_reads import (
    resolve_completed_step_uuids,
    resolve_succeeded_requirement_uuids,
)
from learn_to_cloud_shared.requirements import load_requirement_index
from learn_to_cloud_shared.schemas import (
    LearningProgress,
    LearningStep,
    Phase,
    PhaseOverview,
    PhaseProgress,
    PhaseProgressData,
    Topic,
    TopicProgressData,
    UserProgress,
    VerificationProgress,
)
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)


def _count_by_phase(
    uuids: Iterable[UUID], phase_order_by_uuid: Mapping[UUID, int]
) -> dict[int, int]:
    counts: dict[int, int] = defaultdict(int)
    for uuid in uuids:
        phase_order = phase_order_by_uuid.get(uuid)
        if phase_order is not None:
            counts[phase_order] += 1
    return counts


async def fetch_user_progress(
    db: AsyncSession,
    user_id: int,
    *,
    phase_overview: tuple[PhaseOverview, ...] | None = None,
) -> UserProgress:
    """Fetch complete progress data for a user, via authoritative learner-state reads.

    Reads only ``learner_step_completions``/``verification_attempts`` UUIDs
    for this user, then groups them by phase order in Python using
    the packaged catalog's ``phase_order_by_step_uuid`` /
    ``phase_order_by_requirement_uuid`` maps. A stale/retired UUID (not in
    the catalog) is simply absent from those maps and drops out.

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

    completed_step_uuids = await resolve_completed_step_uuids(
        db, user_id, catalog.active_step_uuids
    )
    completed_steps_by_phase = _count_by_phase(
        completed_step_uuids, catalog.phase_order_by_step_uuid
    )
    succeeded_req_uuids = await resolve_succeeded_requirement_uuids(
        db, user_id, catalog.active_requirement_uuids
    )
    succeeded_by_phase = _count_by_phase(
        succeeded_req_uuids, catalog.phase_order_by_requirement_uuid
    )

    phase_progress_map: dict[int, PhaseProgress] = {}
    for phase in phase_overview:
        phase_progress_map[phase.order] = PhaseProgress(
            phase_id=phase.order,
            learning=LearningProgress(
                steps_completed=completed_steps_by_phase.get(phase.order, 0),
                steps_required=required_steps_by_phase.get(phase.order, 0),
            ),
            verification=VerificationProgress(
                requirements_verified=succeeded_by_phase.get(phase.order, 0),
                requirements_required=len(
                    req_index.requirements_for_phase(phase.order)
                ),
            ),
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
    all_step_uuids = [
        step.uuid for topic in phase.topics for step in topic.learning_steps
    ]
    completed_step_uuids = await resolve_completed_step_uuids(
        db, user_id, all_step_uuids
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
        succeeded = await resolve_succeeded_requirement_uuids(
            db, user_id, current_req_uuids
        )
        hands_on_validated = len(succeeded)

    return PhaseProgress(
        phase_id=phase.order,
        learning=LearningProgress(
            steps_completed=total_completed,
            steps_required=total_steps,
        ),
        verification=VerificationProgress(
            requirements_verified=hands_on_validated,
            requirements_required=hands_on_required,
        ),
        topic_progress=topic_progress,
    )


def phase_progress_to_data(progress: PhaseProgress) -> PhaseProgressData:
    """Convert PhaseProgress to PhaseProgressData response model."""
    return PhaseProgressData(
        learning=progress.learning,
        verification=progress.verification,
        is_complete=progress.is_complete,
        status=progress.status,
    )


def find_first_incomplete_step(
    phase: Phase, completed_step_uuids: set[UUID]
) -> tuple[Topic, LearningStep] | None:
    """First not-yet-checked learning step in topic/step order, or ``None``.

    ``None`` means every step in ``phase`` is checked (including trivially,
    when the phase has no steps at all) -- the caller should point the
    learner at verification instead.
    """
    for topic in phase.topics:
        for step in topic.learning_steps:
            if step.uuid not in completed_step_uuids:
                return topic, step
    return None


async def resolve_continue_destination(
    db: AsyncSession,
    user_id: int,
    phase: Phase,
) -> str:
    """Where the dashboard's "Continue" action should send this learner.

    Points at the first unchecked step's topic, since that's where a
    learner actually left off -- falls back to the phase's verification
    section once every current step is checked.
    """
    all_step_uuids = [
        step.uuid for topic in phase.topics for step in topic.learning_steps
    ]
    completed_step_uuids = await resolve_completed_step_uuids(
        db, user_id, all_step_uuids
    )
    first_incomplete = find_first_incomplete_step(phase, completed_step_uuids)
    if first_incomplete is not None:
        topic, _step = first_incomplete
        return f"/phase/{phase.order}/{topic.slug}"
    if (
        phase.hands_on_verification is not None
        and phase.hands_on_verification.requirements
    ):
        return f"/phase/{phase.order}#verification-section"
    return f"/phase/{phase.order}"
