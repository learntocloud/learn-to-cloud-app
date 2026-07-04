"""DB-backed curriculum loader (issue #464 / Phase C).

Reads the curriculum tree (phases, topics, steps, learning_objectives,
requirements) from the DB tables populated by ``content_sync.py``, and
rebuilds the same Pydantic shape that the YAML loader returns from
``content_service.get_all_phases()``.

This module is intentionally **uncached**. The Phase C decision was to
drop the YAML loader's ``@lru_cache`` rather than carry it forward: the
DB query is fast (~466 active rows in our largest curriculum, all
indexed) and a cache without invalidation creates a class of
stale-data bugs we want to avoid.

In Phase C PR 1 (this module's introduction) the public API in
``content_service.py`` still goes through the YAML loader. PR 2 will
flip the switch.

Soft-deleted rows (``deleted_at IS NOT NULL``) are excluded everywhere.
"""

from __future__ import annotations

import logging
from collections import defaultdict
from collections.abc import Sequence
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from learn_to_cloud_shared.models import (
    CurriculumLearningObjective,
    CurriculumPhase,
    CurriculumRequirement,
    CurriculumStep,
    CurriculumTopic,
)
from learn_to_cloud_shared.schemas import (
    HandsOnRequirement,
    HandsOnRequirementAdapter,
    LearningObjective,
    LearningStep,
    Phase,
    PhaseHandsOnVerificationOverview,
    PhaseOverview,
    Topic,
    TopicOverview,
)

logger = logging.getLogger(__name__)


async def load_all_phases_from_db(db: AsyncSession) -> tuple[Phase, ...]:
    """Build the full curriculum tree from active DB rows.

    Returns phases ordered by ``order``. Nested topics, steps,
    learning_objectives, and requirements are likewise ordered by their
    own ``order`` columns.

    Uses 5 simple queries (one per table) and assembles the tree in
    Python via dict-based grouping by parent UUID. This avoids the
    fanout problems of a single JOIN over five tables and keeps each
    query a straightforward index scan.
    """
    phase_rows = (
        await db.scalars(
            select(CurriculumPhase)
            .where(CurriculumPhase.deleted_at.is_(None))
            .order_by(CurriculumPhase.order)
        )
    ).all()

    topic_rows = (
        await db.scalars(
            select(CurriculumTopic)
            .where(CurriculumTopic.deleted_at.is_(None))
            .order_by(CurriculumTopic.order)
        )
    ).all()

    step_rows = (
        await db.scalars(
            select(CurriculumStep)
            .where(CurriculumStep.deleted_at.is_(None))
            .order_by(CurriculumStep.order)
        )
    ).all()

    objective_rows = (
        await db.scalars(
            select(CurriculumLearningObjective)
            .where(CurriculumLearningObjective.deleted_at.is_(None))
            .order_by(CurriculumLearningObjective.order)
        )
    ).all()

    requirement_rows = (
        await db.scalars(
            select(CurriculumRequirement)
            .where(CurriculumRequirement.deleted_at.is_(None))
            .order_by(CurriculumRequirement.order)
        )
    ).all()

    return _assemble_phases(
        phase_rows=phase_rows,
        topic_rows=topic_rows,
        step_rows=step_rows,
        objective_rows=objective_rows,
        requirement_rows=requirement_rows,
    )


async def load_phase_by_slug_from_db(db: AsyncSession, slug: str) -> Phase | None:
    """Return the active phase with the given slug, or None.

    Scoped to a single phase: looks up just that phase's row, then only
    its own descendant topics/steps/objectives/requirements, instead of
    loading every phase in the curriculum and filtering in Python.
    """
    phase_row = (
        await db.scalars(
            select(CurriculumPhase).where(
                CurriculumPhase.slug == slug,
                CurriculumPhase.deleted_at.is_(None),
            )
        )
    ).one_or_none()
    if phase_row is None:
        return None
    return await _load_phase_subtree(db, phase_row)


async def _load_phase_subtree(db: AsyncSession, phase_row: CurriculumPhase) -> Phase:
    """Load one phase's descendants and assemble it into a ``Phase``."""
    topic_rows = (
        await db.scalars(
            select(CurriculumTopic)
            .where(
                CurriculumTopic.phase_uuid == phase_row.uuid,
                CurriculumTopic.deleted_at.is_(None),
            )
            .order_by(CurriculumTopic.order)
        )
    ).all()
    topic_uuids = [t.uuid for t in topic_rows]

    step_rows: Sequence[CurriculumStep] = ()
    objective_rows: Sequence[CurriculumLearningObjective] = ()
    if topic_uuids:
        step_rows = (
            await db.scalars(
                select(CurriculumStep)
                .where(
                    CurriculumStep.topic_uuid.in_(topic_uuids),
                    CurriculumStep.deleted_at.is_(None),
                )
                .order_by(CurriculumStep.order)
            )
        ).all()
        objective_rows = (
            await db.scalars(
                select(CurriculumLearningObjective)
                .where(
                    CurriculumLearningObjective.topic_uuid.in_(topic_uuids),
                    CurriculumLearningObjective.deleted_at.is_(None),
                )
                .order_by(CurriculumLearningObjective.order)
            )
        ).all()

    requirement_rows = (
        await db.scalars(
            select(CurriculumRequirement)
            .where(
                CurriculumRequirement.phase_uuid == phase_row.uuid,
                CurriculumRequirement.deleted_at.is_(None),
            )
            .order_by(CurriculumRequirement.order)
        )
    ).all()

    (phase,) = _assemble_phases(
        phase_rows=[phase_row],
        topic_rows=topic_rows,
        step_rows=step_rows,
        objective_rows=objective_rows,
        requirement_rows=requirement_rows,
    )
    return phase


async def load_topic_by_uuid_from_db(
    db: AsyncSession, topic_uuid: UUID
) -> Topic | None:
    """Return the active topic with the given uuid, or None.

    Scoped to the single topic's own steps/objectives, not the whole
    curriculum tree.
    """
    topic_row = (
        await db.scalars(
            select(CurriculumTopic).where(
                CurriculumTopic.uuid == topic_uuid,
                CurriculumTopic.deleted_at.is_(None),
            )
        )
    ).one_or_none()
    if topic_row is None:
        return None
    return await _load_topic_subtree(db, topic_row)


async def _load_topic_subtree(db: AsyncSession, topic_row: CurriculumTopic) -> Topic:
    """Load one topic's steps/objectives and assemble it into a ``Topic``."""
    step_rows = (
        await db.scalars(
            select(CurriculumStep)
            .where(
                CurriculumStep.topic_uuid == topic_row.uuid,
                CurriculumStep.deleted_at.is_(None),
            )
            .order_by(CurriculumStep.order)
        )
    ).all()
    objective_rows = (
        await db.scalars(
            select(CurriculumLearningObjective)
            .where(
                CurriculumLearningObjective.topic_uuid == topic_row.uuid,
                CurriculumLearningObjective.deleted_at.is_(None),
            )
            .order_by(CurriculumLearningObjective.order)
        )
    ).all()
    return _build_topic(
        topic_row,
        learning_steps=[_build_step(row) for row in step_rows],
        learning_objectives=[_build_objective(row) for row in objective_rows],
    )


async def load_topic_by_slugs_from_db(
    db: AsyncSession, phase_slug: str, topic_slug: str
) -> Topic | None:
    """Return the active topic by ``(phase_slug, topic_slug)``.

    Scoped queries only: looks up the phase, then just that topic
    within it, never the full curriculum tree.
    """
    phase_row = (
        await db.scalars(
            select(CurriculumPhase).where(
                CurriculumPhase.slug == phase_slug,
                CurriculumPhase.deleted_at.is_(None),
            )
        )
    ).one_or_none()
    if phase_row is None:
        return None
    topic_row = (
        await db.scalars(
            select(CurriculumTopic).where(
                CurriculumTopic.phase_uuid == phase_row.uuid,
                CurriculumTopic.slug == topic_slug,
                CurriculumTopic.deleted_at.is_(None),
            )
        )
    ).one_or_none()
    if topic_row is None:
        return None
    return await _load_topic_subtree(db, topic_row)


async def load_topic_containing_step_from_db(
    db: AsyncSession, step_uuid: UUID
) -> tuple[Topic, LearningStep] | None:
    """Resolve a step UUID to its parent topic (with all sibling steps).

    One indexed lookup for the owning ``topic_uuid``, then loads only
    that topic's subtree. Used to check a single step complete/
    incomplete without walking a fully-loaded multi-phase tree.
    """
    topic_uuid = (
        await db.scalars(
            select(CurriculumStep.topic_uuid).where(
                CurriculumStep.uuid == step_uuid,
                CurriculumStep.deleted_at.is_(None),
            )
        )
    ).one_or_none()
    if topic_uuid is None:
        return None
    topic = await load_topic_by_uuid_from_db(db, topic_uuid)
    if topic is None:
        return None
    step = next((s for s in topic.learning_steps if s.uuid == step_uuid), None)
    if step is None:
        return None
    return topic, step


async def load_curriculum_overview_from_db(
    db: AsyncSession,
) -> tuple[PhaseOverview, ...]:
    """Load a lightweight phase+topic overview for browse-level pages.

    No steps/objectives/requirements are loaded here -- the home and
    curriculum listing pages only ever render phase name/description
    and topic names, never step-level content. 2 small queries instead
    of the full 5-table, ~466-row assembly.
    """
    phase_rows = (
        await db.scalars(
            select(CurriculumPhase)
            .where(CurriculumPhase.deleted_at.is_(None))
            .order_by(CurriculumPhase.order)
        )
    ).all()
    topic_rows = (
        await db.scalars(
            select(CurriculumTopic)
            .where(CurriculumTopic.deleted_at.is_(None))
            .order_by(CurriculumTopic.order)
        )
    ).all()

    topics_by_phase: dict[UUID, list[TopicOverview]] = defaultdict(list)
    for topic_row in topic_rows:
        topics_by_phase[topic_row.phase_uuid].append(
            TopicOverview(uuid=topic_row.uuid, slug=topic_row.slug, name=topic_row.name)
        )

    return tuple(
        PhaseOverview(
            uuid=phase_row.uuid,
            order=phase_row.order,
            name=phase_row.name,
            slug=phase_row.slug,
            description=phase_row.description,
            short_description=phase_row.short_description,
            topics=topics_by_phase.get(phase_row.uuid, []),
        )
        for phase_row in phase_rows
    )


async def load_requirements_by_phase_order_from_db(
    db: AsyncSession,
    *,
    phase_order_by_uuid: dict[UUID, int] | None = None,
) -> dict[int, list[HandsOnRequirement]]:
    """Load all active requirements, grouped by parent phase order.

    Only queries ``requirements`` + ``phases`` (~18 rows total in
    production), not the full curriculum tree, so gating checks and
    the requirement index don't pay for 450+ unrelated step/topic rows
    just to reach 10 requirement rows.

    Callers that already have a phase order mapping in hand (e.g. from
    ``load_curriculum_overview_from_db``) can pass it via
    ``phase_order_by_uuid`` to skip the redundant phases query.
    """
    if phase_order_by_uuid is None:
        phase_rows = (
            await db.scalars(
                select(CurriculumPhase).where(CurriculumPhase.deleted_at.is_(None))
            )
        ).all()
        phase_order_by_uuid = {row.uuid: row.order for row in phase_rows}

    requirement_rows = (
        await db.scalars(
            select(CurriculumRequirement)
            .where(CurriculumRequirement.deleted_at.is_(None))
            .order_by(CurriculumRequirement.order)
        )
    ).all()

    by_phase_order: dict[int, list[HandsOnRequirement]] = defaultdict(list)
    for row in requirement_rows:
        phase_order = phase_order_by_uuid.get(row.phase_uuid)
        if phase_order is None:
            continue
        by_phase_order[phase_order].append(_build_requirement(row))
    return dict(by_phase_order)


async def load_requirement_counts_by_phase_from_db(
    db: AsyncSession,
) -> dict[int, int]:
    """Count active requirements per phase via one aggregate query.

    Requirement-side mirror of ``load_required_step_counts_by_phase_from_db``.
    Backs hands-on totals (``hands_on_required``) and the ``/stats``
    phase-completion check without assembling the requirement tree.
    """
    result = await db.execute(
        select(CurriculumPhase.order, func.count(CurriculumRequirement.uuid))
        .select_from(CurriculumRequirement)
        .join(
            CurriculumPhase,
            CurriculumRequirement.phase_uuid == CurriculumPhase.uuid,
        )
        .where(
            CurriculumRequirement.deleted_at.is_(None),
            CurriculumPhase.deleted_at.is_(None),
        )
        .group_by(CurriculumPhase.order)
    )
    return {order: count for order, count in result.all()}


async def load_required_step_counts_by_phase_from_db(
    db: AsyncSession,
) -> dict[int, int]:
    """Count active steps per phase via one aggregate query.

    Backs progress totals (``steps_required``) without assembling the
    full nested Pydantic tree.
    """
    result = await db.execute(
        select(CurriculumPhase.order, func.count(CurriculumStep.uuid))
        .select_from(CurriculumStep)
        .join(CurriculumTopic, CurriculumStep.topic_uuid == CurriculumTopic.uuid)
        .join(CurriculumPhase, CurriculumTopic.phase_uuid == CurriculumPhase.uuid)
        .where(
            CurriculumStep.deleted_at.is_(None),
            CurriculumTopic.deleted_at.is_(None),
            CurriculumPhase.deleted_at.is_(None),
        )
        .group_by(CurriculumPhase.order)
    )
    return {order: count for order, count in result.all()}


# ---------------------------------------------------------------------------
# Internal assembly helpers
# ---------------------------------------------------------------------------


def _assemble_phases(
    *,
    phase_rows: Sequence[CurriculumPhase],
    topic_rows: Sequence[CurriculumTopic],
    step_rows: Sequence[CurriculumStep],
    objective_rows: Sequence[CurriculumLearningObjective],
    requirement_rows: Sequence[CurriculumRequirement],
) -> tuple[Phase, ...]:
    """Build the full Pydantic tree from already-loaded ORM rows."""
    steps_by_topic: dict[UUID, list[LearningStep]] = defaultdict(list)
    for step_row in step_rows:
        steps_by_topic[step_row.topic_uuid].append(_build_step(step_row))

    objectives_by_topic: dict[UUID, list[LearningObjective]] = defaultdict(list)
    for obj_row in objective_rows:
        objectives_by_topic[obj_row.topic_uuid].append(_build_objective(obj_row))

    topics_by_phase: dict[UUID, list[Topic]] = defaultdict(list)
    for topic_row in topic_rows:
        topics_by_phase[topic_row.phase_uuid].append(
            _build_topic(
                topic_row,
                learning_steps=steps_by_topic.get(topic_row.uuid, []),
                learning_objectives=objectives_by_topic.get(topic_row.uuid, []),
            )
        )

    requirements_by_phase: dict[UUID, list] = defaultdict(list)
    for req_row in requirement_rows:
        requirements_by_phase[req_row.phase_uuid].append(_build_requirement(req_row))

    phases: list[Phase] = []
    for phase_row in phase_rows:
        phase_topics = topics_by_phase.get(phase_row.uuid, [])
        phase_requirements = requirements_by_phase.get(phase_row.uuid, [])
        phases.append(
            _build_phase(
                phase_row,
                topics=phase_topics,
                requirements=phase_requirements,
            )
        )
    return tuple(phases)


def _build_step(row: CurriculumStep) -> LearningStep:
    # extra_config holds the non-core fields (options, checklist, tips,
    # done_when) bundled into one JSONB column. Spread it back into the
    # step payload so LearningStep.model_validate sees the same shape it
    # would from YAML.
    payload: dict = {
        "uuid": row.uuid,
        "slug": row.slug,
        "order": row.order,
        "action": row.action,
        "title": row.title,
        "url": row.url,
        "description": row.description,
        "code": row.code,
    }
    payload.update(row.extra_config or {})
    return LearningStep.model_validate(payload)


def _build_objective(row: CurriculumLearningObjective) -> LearningObjective:
    return LearningObjective.model_validate(
        {
            "uuid": row.uuid,
            "text": row.text_,
            "order": row.order,
        }
    )


def _build_topic(
    row: CurriculumTopic,
    *,
    learning_steps: list[LearningStep],
    learning_objectives: list[LearningObjective],
) -> Topic:
    return Topic.model_validate(
        {
            "uuid": row.uuid,
            "slug": row.slug,
            "name": row.name,
            "description": row.description,
            "order": row.order,
            "learning_steps": learning_steps,
            "learning_objectives": learning_objectives,
        }
    )


def _build_requirement(row: CurriculumRequirement):
    """Rehydrate a HandsOnRequirement via the discriminated union.

    The submission_type discriminator picks the right subclass; the
    type_config JSONB dict is validated against that subclass's
    per-type config model.
    """
    return HandsOnRequirementAdapter.validate_python(
        {
            "uuid": row.uuid,
            "slug": row.slug,
            "submission_type": row.submission_type,
            "name": row.name,
            "description": row.description,
            "type_config": row.type_config or {},
        }
    )


def _build_phase(
    row: CurriculumPhase,
    *,
    topics: list[Topic],
    requirements: list,
) -> Phase:
    hov: PhaseHandsOnVerificationOverview | None = None
    if requirements:
        hov = PhaseHandsOnVerificationOverview(
            requirement_slugs=[r.slug for r in requirements],
            requirements=requirements,
        )
    return Phase.model_validate(
        {
            "uuid": row.uuid,
            "slug": row.slug,
            "name": row.name,
            "description": row.description,
            "short_description": row.short_description,
            "order": row.order,
            "topic_slugs": [t.slug for t in topics],
            "topics": topics,
            "hands_on_verification": hov,
        }
    )
