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

Data sources:
- Step completions: ``learner_step_completions`` table (authoritative), with
  a narrow ``step_progress`` legacy fallback for steps not yet mirrored.
- Hands-on validations: ``verification_attempts`` table (authoritative --
  ``outcome == 'succeeded'`` only), with a narrow ``submissions`` legacy
  fallback for requirements that have no attempt row at all yet.
- Curriculum shape: packaged catalog via ``content_service`` (in-memory,
  no DB reads)

The legacy fallback exists only for records not yet reconciled/mirrored
during the PR5/PR6 mixed-revision window -- a requirement or step with an
authoritative row always wins, regardless of legacy state. Fallback usage is
logged (``progress.legacy_fallback_used``) and surfaced on the typed
``LearningProgress``/``VerificationProgress`` models so PR8 can detect when
the fallback path is no longer exercised and remove it.
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
    for this user (no curriculum-table joins), plus a narrow legacy fallback
    query for either source, then groups them by phase order in Python using
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

    completed_step_uuids, fallback_step_uuids = await resolve_completed_step_uuids(
        db, user_id, catalog.active_step_uuids
    )
    completed_steps_by_phase = _count_by_phase(
        completed_step_uuids, catalog.phase_order_by_step_uuid
    )
    fallback_steps_by_phase = _count_by_phase(
        fallback_step_uuids, catalog.phase_order_by_step_uuid
    )

    succeeded_req_uuids, fallback_req_uuids = await resolve_succeeded_requirement_uuids(
        db, user_id, catalog.active_requirement_uuids
    )
    succeeded_by_phase = _count_by_phase(
        succeeded_req_uuids, catalog.phase_order_by_requirement_uuid
    )
    fallback_reqs_by_phase = _count_by_phase(
        fallback_req_uuids, catalog.phase_order_by_requirement_uuid
    )

    phase_progress_map: dict[int, PhaseProgress] = {}
    for phase in phase_overview:
        phase_progress_map[phase.order] = PhaseProgress(
            phase_id=phase.order,
            learning=LearningProgress(
                steps_completed=completed_steps_by_phase.get(phase.order, 0),
                steps_required=required_steps_by_phase.get(phase.order, 0),
                legacy_fallback_steps=fallback_steps_by_phase.get(phase.order, 0),
            ),
            verification=VerificationProgress(
                requirements_verified=succeeded_by_phase.get(phase.order, 0),
                requirements_required=len(
                    req_index.requirements_for_phase(phase.order)
                ),
                legacy_fallback_requirements=fallback_reqs_by_phase.get(phase.order, 0),
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
    completed_step_uuids, fallback_step_uuids = await resolve_completed_step_uuids(
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
    fallback_req_count = 0
    if hands_on_required > 0:
        succeeded, fallback_only = await resolve_succeeded_requirement_uuids(
            db, user_id, current_req_uuids
        )
        hands_on_validated = len(succeeded)
        fallback_req_count = len(fallback_only)

    return PhaseProgress(
        phase_id=phase.order,
        learning=LearningProgress(
            steps_completed=total_completed,
            steps_required=total_steps,
            legacy_fallback_steps=len(fallback_step_uuids),
        ),
        verification=VerificationProgress(
            requirements_verified=hands_on_validated,
            requirements_required=hands_on_required,
            legacy_fallback_requirements=fallback_req_count,
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
