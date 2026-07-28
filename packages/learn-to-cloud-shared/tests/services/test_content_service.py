"""Unit tests for the catalog-backed curriculum read API.

These are pure in-memory lookups over the process-level
``CurriculumCatalog`` singleton (the real packaged artifact), so no DB
or mocking is needed -- every function here is synchronous.
"""

from __future__ import annotations

from uuid import uuid4

import pytest

from learn_to_cloud_shared.content_catalog import get_curriculum_catalog
from learn_to_cloud_shared.content_service import (
    get_all_phases,
    get_curriculum_overview,
    get_phase_by_slug,
    get_required_step_counts_by_phase,
    get_requirement_counts_by_phase,
    get_requirements_by_phase_order,
    get_topic_containing_step,
)

pytestmark = pytest.mark.unit


class TestGetAllPhases:
    def test_returns_catalog_phases(self):
        assert get_all_phases() == get_curriculum_catalog().phases


class TestGetPhaseBySlug:
    def test_known_slug_returns_phase(self):
        phase = get_phase_by_slug("phase0")
        assert phase is not None
        assert phase.slug == "phase0"

    def test_unknown_slug_returns_none(self):
        assert get_phase_by_slug("not-a-real-phase") is None


class TestGetCurriculumOverview:
    def test_matches_phase_shape_without_step_content(self):
        catalog = get_curriculum_catalog()
        overview = get_curriculum_overview()

        assert len(overview) == len(catalog.phases)
        for phase_overview, phase in zip(overview, catalog.phases, strict=True):
            assert phase_overview.uuid == phase.uuid
            assert phase_overview.order == phase.order
            assert phase_overview.slug == phase.slug
            assert phase_overview.name == phase.name
            assert [t.uuid for t in phase_overview.topics] == [
                t.uuid for t in phase.topics
            ]


class TestGetTopicContainingStep:
    def test_known_step_resolves_to_parent_topic(self):
        catalog = get_curriculum_catalog()
        phase = next(p for p in catalog.phases if p.topics)
        topic = next(t for t in phase.topics if t.learning_steps)
        step = topic.learning_steps[0]

        result = get_topic_containing_step(step.uuid)

        assert result is not None
        found_topic, found_step = result
        assert found_topic.uuid == topic.uuid
        assert found_step.uuid == step.uuid

    def test_unknown_step_uuid_returns_none(self):
        assert get_topic_containing_step(uuid4()) is None


class TestGetRequirementsByPhaseOrder:
    def test_only_includes_phases_with_requirements(self):
        catalog = get_curriculum_catalog()
        by_order = get_requirements_by_phase_order()

        for phase in catalog.phases:
            expected = catalog.requirements_by_phase_slug.get(phase.slug, ())
            if expected:
                assert by_order[phase.order] == list(expected)
            else:
                assert phase.order not in by_order


class TestGetRequiredStepCountsByPhase:
    def test_counts_match_catalog_steps_by_phase(self):
        catalog = get_curriculum_catalog()
        counts = get_required_step_counts_by_phase()

        for phase in catalog.phases:
            assert counts[phase.order] == len(
                catalog.steps_by_phase_slug.get(phase.slug, ())
            )


class TestGetRequirementCountsByPhase:
    def test_counts_match_catalog_requirements_by_phase(self):
        catalog = get_curriculum_catalog()
        counts = get_requirement_counts_by_phase()

        for phase in catalog.phases:
            assert counts[phase.order] == len(
                catalog.requirements_by_phase_slug.get(phase.slug, ())
            )
