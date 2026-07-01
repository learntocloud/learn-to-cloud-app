"""Public curriculum read API (DB-backed).

After Phase C (issue #461), runtime reads in the API go through the DB
loader populated at deploy time by ``content_sync.py``. This module
provides the thin async wrappers callers use: pass an
``AsyncSession`` and get back the same Pydantic shape the YAML loader
used to return.

Per-request loads are uncached by design -- the curriculum is small
(~466 active rows, all indexed, 5 simple SELECTs) and a process-level
cache without invalidation creates a class of stale-data bugs we want
to avoid.

For the deploy-time YAML to DB sync and the strict cross-file
validators, use ``learn_to_cloud_shared.content_yaml_loader``.
"""

from __future__ import annotations

from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from learn_to_cloud_shared.content_db_loader import (
    load_all_phases_from_db,
    load_curriculum_overview_from_db,
    load_phase_by_slug_from_db,
    load_required_step_counts_by_phase_from_db,
    load_requirements_by_phase_order_from_db,
    load_topic_containing_step_from_db,
)
from learn_to_cloud_shared.schemas import (
    HandsOnRequirement,
    LearningStep,
    Phase,
    PhaseOverview,
    Topic,
)


async def get_all_phases(db: AsyncSession) -> tuple[Phase, ...]:
    """Get all active phases in order, with nested topics and requirements."""
    return await load_all_phases_from_db(db)


async def get_phase_by_slug(db: AsyncSession, slug: str) -> Phase | None:
    """Get a phase by its slug (e.g. ``phase1``)."""
    return await load_phase_by_slug_from_db(db, slug)


async def get_curriculum_overview(db: AsyncSession) -> tuple[PhaseOverview, ...]:
    """Get the lightweight phase+topic overview for browse-level pages.

    No step/objective/requirement content -- see ``PhaseOverview``.
    """
    return await load_curriculum_overview_from_db(db)


async def get_topic_containing_step(
    db: AsyncSession, step_uuid: UUID
) -> tuple[Topic, LearningStep] | None:
    """Resolve a step UUID to its parent topic (with sibling steps).

    Scoped to one topic's subtree, not the full curriculum tree.
    """
    return await load_topic_containing_step_from_db(db, step_uuid)


async def get_requirements_by_phase_order(
    db: AsyncSession,
    *,
    phase_order_by_uuid: dict[UUID, int] | None = None,
) -> dict[int, list[HandsOnRequirement]]:
    """Get all active requirements grouped by parent phase order.

    Scoped to the ``requirements``/``phases`` tables only, not the full
    curriculum tree. Pass ``phase_order_by_uuid`` when the caller
    already has one (e.g. from ``get_curriculum_overview``) to skip a
    redundant phases query.
    """
    return await load_requirements_by_phase_order_from_db(
        db, phase_order_by_uuid=phase_order_by_uuid
    )


async def get_required_step_counts_by_phase(db: AsyncSession) -> dict[int, int]:
    """Get the count of active required steps per phase order."""
    return await load_required_step_counts_by_phase_from_db(db)
