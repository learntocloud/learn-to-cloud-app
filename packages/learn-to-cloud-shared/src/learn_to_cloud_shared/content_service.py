"""Public curriculum read API (catalog-backed).

Runtime reads in the API go through the packaged, process-level
:class:`~learn_to_cloud_shared.content_catalog.CurriculumCatalog`
instead of the database. The catalog is loaded once per process (at
startup, and lazily via ``get_curriculum_catalog``'s ``lru_cache``), so
every function here is a synchronous, in-memory lookup -- no
``AsyncSession``, no I/O.

The PostgreSQL curriculum tables and ``content_db_loader.py`` remain in
place (populated at deploy time by ``content_sync.py``) as a
compatibility shadow, but no request path reads them.

For the deploy-time YAML to DB sync and the strict cross-file
validators, use ``learn_to_cloud_shared.content_yaml_loader``.
"""

from __future__ import annotations

from uuid import UUID

from learn_to_cloud_shared.content_catalog import get_curriculum_catalog
from learn_to_cloud_shared.schemas import (
    HandsOnRequirement,
    LearningStep,
    Phase,
    PhaseOverview,
    Topic,
    TopicOverview,
)


def get_all_phases() -> tuple[Phase, ...]:
    """Get all phases in order, with nested topics and requirements."""
    return get_curriculum_catalog().phases


def get_phase_by_slug(slug: str) -> Phase | None:
    """Get a phase by its slug (e.g. ``phase1``)."""
    return get_curriculum_catalog().phases_by_slug.get(slug)


def get_curriculum_overview() -> tuple[PhaseOverview, ...]:
    """Get the lightweight phase+topic overview for browse-level pages.

    No step/objective/requirement content -- see ``PhaseOverview``.
    """
    catalog = get_curriculum_catalog()
    return tuple(
        PhaseOverview(
            uuid=phase.uuid,
            order=phase.order,
            name=phase.name,
            slug=phase.slug,
            description=phase.description,
            short_description=phase.short_description,
            topics=[
                TopicOverview(uuid=topic.uuid, slug=topic.slug, name=topic.name)
                for topic in phase.topics
            ],
        )
        for phase in catalog.phases
    )


def get_topic_containing_step(step_uuid: UUID) -> tuple[Topic, LearningStep] | None:
    """Resolve a step UUID to its parent topic (with sibling steps)."""
    catalog = get_curriculum_catalog()
    step = catalog.steps_by_uuid.get(step_uuid)
    if step is None:
        return None
    topic = catalog.topic_by_step_uuid.get(step_uuid)
    if topic is None:
        return None
    return topic, step


def get_requirements_by_phase_order() -> dict[int, list[HandsOnRequirement]]:
    """Get all requirements grouped by parent phase order."""
    catalog = get_curriculum_catalog()
    return {
        phase.order: list(catalog.requirements_by_phase_slug.get(phase.slug, ()))
        for phase in catalog.phases
        if catalog.requirements_by_phase_slug.get(phase.slug)
    }


def get_required_step_counts_by_phase() -> dict[int, int]:
    """Get the count of required steps per phase order."""
    catalog = get_curriculum_catalog()
    return {
        phase.order: len(catalog.steps_by_phase_slug.get(phase.slug, ()))
        for phase in catalog.phases
    }


def get_requirement_counts_by_phase() -> dict[int, int]:
    """Get the count of hands-on requirements per phase order."""
    catalog = get_curriculum_catalog()
    return {
        phase.order: len(catalog.requirements_by_phase_slug.get(phase.slug, ()))
        for phase in catalog.phases
    }
