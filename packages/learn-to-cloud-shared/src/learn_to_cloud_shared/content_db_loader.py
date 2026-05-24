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

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from learn_to_cloud_shared.models import (
    CurriculumLearningObjective,
    CurriculumPhase,
    CurriculumRequirement,
    CurriculumStep,
    CurriculumTopic,
)
from learn_to_cloud_shared.schemas import (
    HandsOnRequirementAdapter,
    LearningObjective,
    LearningStep,
    Phase,
    PhaseHandsOnVerificationOverview,
    Topic,
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

    Routes through ``load_all_phases_from_db`` so the visibility rules
    (active topics inside active phases, etc.) are guaranteed identical.
    Trivially cheap given curriculum size.
    """
    for phase in await load_all_phases_from_db(db):
        if phase.slug == slug:
            return phase
    return None


async def load_topic_by_id_from_db(db: AsyncSession, topic_id: str) -> Topic | None:
    """Return the active topic with the given legacy_id, or None.

    Routes through ``load_all_phases_from_db`` for consistency.
    """
    for phase in await load_all_phases_from_db(db):
        for topic in phase.topics:
            if topic.id == topic_id:
                return topic
    return None


async def load_topic_by_slugs_from_db(
    db: AsyncSession, phase_slug: str, topic_slug: str
) -> Topic | None:
    """Return the active topic by ``(phase_slug, topic_slug)``."""
    phase = await load_phase_by_slug_from_db(db, phase_slug)
    if phase is None:
        return None
    for topic in phase.topics:
        if topic.slug == topic_slug:
            return topic
    return None


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
        "id": row.legacy_id,
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
            "id": row.legacy_id,
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
            "id": row.legacy_id,
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
            "id": row.id,
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
            requirement_slugs=[r.id for r in requirements],
            requirements=requirements,
        )
    return Phase.model_validate(
        {
            "uuid": row.uuid,
            "id": row.legacy_id,
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
