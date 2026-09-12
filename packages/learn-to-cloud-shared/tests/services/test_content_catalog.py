"""Unit tests for the curriculum catalog (process-level artifact reader).

Covers:
- Catalog lookup indices (by UUID, by slug, by phase, active sets)
- Loading the real packaged artifact end to end
- Schema compatibility (artifact_schema_version mismatch fails fast)
- Strict failure on a missing/corrupted/tampered artifact
- Process-level singleton caching
"""

from __future__ import annotations

import json
from copy import deepcopy
from unittest.mock import patch

import pytest

from learn_to_cloud_shared.content_catalog import (
    CurriculumCatalog,
    CurriculumCatalogError,
    get_curriculum_catalog,
    load_curriculum_catalog,
)
from learn_to_cloud_shared.content_compiler import (
    ARTIFACT_SCHEMA_VERSION,
    compile_curriculum_artifact,
    compute_content_hash,
)

pytestmark = pytest.mark.unit


@pytest.fixture(autouse=True)
def _clear_catalog_cache():
    get_curriculum_catalog.cache_clear()
    yield
    get_curriculum_catalog.cache_clear()


@pytest.fixture(scope="module")
def compiled_payload() -> dict:
    return compile_curriculum_artifact()


@pytest.fixture
def real_payload(compiled_payload: dict) -> dict:
    """Give each test an independent copy of the real compiled curriculum."""
    return deepcopy(compiled_payload)


class _FakeResource:
    """Minimal stand-in for the ``importlib.resources`` Traversable API."""

    def __init__(self, text: str | None):
        self._text = text

    def is_file(self) -> bool:
        return self._text is not None

    def read_text(self, encoding: str = "utf-8") -> str:
        assert self._text is not None
        return self._text

    def joinpath(self, *parts: str) -> _FakeResource:
        return self


def _patched_resource(text: str | None):
    return patch(
        "learn_to_cloud_shared.content_catalog.files",
        autospec=True,
        return_value=_FakeResource(text),
    )


class TestLoadCurriculumCatalog:
    def test_loads_real_packaged_artifact(self):
        """The artifact actually committed to the wheel loads cleanly."""
        catalog = load_curriculum_catalog()
        assert catalog.phases
        assert catalog.artifact_schema_version == ARTIFACT_SCHEMA_VERSION

    def test_every_phase_has_completion_metadata(self):
        catalog = load_curriculum_catalog()

        assert [
            phase.order for phase in catalog.phases if not phase.required_for_graduation
        ] == [7]
        for phase in catalog.phases:
            assert phase.estimated_learning_time.maximum_hours > 0
            assert phase.estimated_project_time.maximum_hours > 0
            assert phase.project_summary
            assert phase.completion_summary
            assert phase.prerequisites
            assert phase.cost_note

    def test_missing_artifact_raises(self):
        with (
            _patched_resource(None),
            pytest.raises(CurriculumCatalogError, match="not found"),
        ):
            load_curriculum_catalog()

    def test_invalid_json_raises(self):
        with (
            _patched_resource("{not valid json"),
            pytest.raises(CurriculumCatalogError, match="not valid JSON"),
        ):
            load_curriculum_catalog()

    def test_non_object_json_raises(self):
        with (
            _patched_resource("[1, 2, 3]"),
            pytest.raises(CurriculumCatalogError, match="JSON object"),
        ):
            load_curriculum_catalog()

    def test_schema_version_mismatch_raises(self, real_payload: dict):
        real_payload["artifact_schema_version"] = ARTIFACT_SCHEMA_VERSION + 1
        real_payload["content_hash"] = compute_content_hash(
            {k: v for k, v in real_payload.items() if k != "content_hash"}
        )
        with (
            _patched_resource(json.dumps(real_payload)),
            pytest.raises(CurriculumCatalogError, match="schema_version"),
        ):
            load_curriculum_catalog()

    def test_missing_content_hash_raises(self, real_payload: dict):
        bad_payload = {k: v for k, v in real_payload.items() if k != "content_hash"}
        with (
            _patched_resource(json.dumps(bad_payload)),
            pytest.raises(CurriculumCatalogError, match="missing content_hash"),
        ):
            load_curriculum_catalog()

    def test_tampered_payload_fails_hash_check(self, real_payload: dict):
        """Hand-editing a field without recomputing the hash must be caught."""
        real_payload["phases"][0]["name"] = "Tampered Name"
        with (
            _patched_resource(json.dumps(real_payload)),
            pytest.raises(CurriculumCatalogError, match="content_hash does not match"),
        ):
            load_curriculum_catalog()


class TestCurriculumCatalogIndices:
    @pytest.fixture
    def catalog(self, real_payload: dict) -> CurriculumCatalog:
        with _patched_resource(json.dumps(real_payload)):
            return load_curriculum_catalog()

    def test_phase_lookup_by_slug(self, catalog: CurriculumCatalog):
        for phase in catalog.phases:
            assert catalog.phases_by_slug[phase.slug] is phase

    def test_step_lookup_by_uuid_and_phase(self, catalog: CurriculumCatalog):
        phase0 = catalog.phases_by_slug["phase0"]
        topic = phase0.topics[0]
        step = topic.learning_steps[0]
        assert catalog.steps_by_uuid[step.uuid] is step
        assert step in catalog.steps_by_phase_slug[phase0.slug]
        assert catalog.topic_by_step_uuid[step.uuid] is topic
        assert catalog.phase_order_by_step_uuid[step.uuid] == phase0.order

    def test_requirement_lookup_by_uuid_and_phase(self, catalog: CurriculumCatalog):
        phase = next(p for p in catalog.phases if p.hands_on_verification)
        req = phase.hands_on_verification.requirements[0]
        assert catalog.requirements_by_uuid[req.uuid] is req
        assert req in catalog.requirements_by_phase_slug[phase.slug]
        assert catalog.phase_order_by_requirement_uuid[req.uuid] == phase.order

    def test_active_uuid_sets_match_curriculum(self, catalog: CurriculumCatalog):
        assert catalog.active_step_uuids == {
            step.uuid
            for phase in catalog.phases
            for topic in phase.topics
            for step in topic.learning_steps
        }
        assert catalog.active_requirement_uuids == {
            requirement.uuid
            for phase in catalog.phases
            if phase.hands_on_verification
            for requirement in phase.hands_on_verification.requirements
        }


class TestCurriculumCatalogImmutability:
    @pytest.fixture
    def catalog(self, real_payload: dict) -> CurriculumCatalog:
        with _patched_resource(json.dumps(real_payload)):
            return load_curriculum_catalog()

    @pytest.mark.parametrize(
        "attr",
        [
            "phases_by_slug",
            "steps_by_uuid",
            "steps_by_phase_slug",
            "topic_by_step_uuid",
            "phase_order_by_step_uuid",
            "requirements_by_uuid",
            "requirements_by_phase_slug",
            "phase_order_by_requirement_uuid",
        ],
    )
    def test_mapping_fields_reject_item_assignment(
        self, catalog: CurriculumCatalog, attr: str
    ):
        mapping = getattr(catalog, attr)
        some_key = next(iter(mapping))
        with pytest.raises(TypeError):
            mapping[some_key] = mapping[some_key]

    def test_dataclass_fields_reject_reassignment(self, catalog: CurriculumCatalog):
        with pytest.raises(AttributeError):
            catalog.curriculum_version = 999


class TestGetCurriculumCatalogSingleton:
    def test_returns_same_instance_across_calls(self):
        first = get_curriculum_catalog()
        second = get_curriculum_catalog()
        assert first is second

    def test_clear_cache_forces_reload(self):
        first = get_curriculum_catalog()
        get_curriculum_catalog.cache_clear()
        second = get_curriculum_catalog()
        assert first is not second
        assert first == second
