"""Unit tests for the curriculum catalog (process-level artifact reader).

Covers:
- Catalog lookup indices (by UUID, by slug, by phase, active sets/counts)
- Loading the real packaged artifact end to end
- Schema compatibility (artifact_schema_version mismatch fails fast)
- Strict failure on a missing/corrupted/tampered artifact
- Process-level singleton caching
"""

from __future__ import annotations

import json
from unittest.mock import patch

import pytest

from learn_to_cloud_shared.content_catalog import (
    CurriculumCatalog,
    CurriculumCatalogError,
    clear_catalog_cache,
    get_curriculum_catalog,
    load_curriculum_catalog,
)
from learn_to_cloud_shared.content_compiler import (
    ARTIFACT_SCHEMA_VERSION,
    compile_curriculum_artifact,
)

pytestmark = pytest.mark.unit


@pytest.fixture(autouse=True)
def _clear_catalog_cache():
    clear_catalog_cache()
    yield
    clear_catalog_cache()


@pytest.fixture
def real_payload() -> dict:
    """Compile the real authored curriculum for use as fake package data."""
    return compile_curriculum_artifact()


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
        assert catalog.phase_count > 0
        assert catalog.artifact_schema_version == ARTIFACT_SCHEMA_VERSION

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
        bad_payload = {**real_payload, "artifact_schema_version": 999}
        with (
            _patched_resource(json.dumps(bad_payload)),
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
        tampered = json.loads(json.dumps(real_payload))
        tampered["phases"][0]["name"] = "Tampered Name"
        with (
            _patched_resource(json.dumps(tampered)),
            pytest.raises(CurriculumCatalogError, match="content_hash does not match"),
        ):
            load_curriculum_catalog()


class TestCurriculumCatalogIndices:
    @pytest.fixture
    def catalog(self, real_payload: dict) -> CurriculumCatalog:
        with _patched_resource(json.dumps(real_payload)):
            return load_curriculum_catalog()

    def test_phase_lookup_by_slug_and_order_agree(self, catalog: CurriculumCatalog):
        phase0 = catalog.phases_by_slug["phase0"]
        assert catalog.phases_by_order[phase0.order] is phase0

    def test_topic_lookup_by_uuid_and_phase_slug_agree(
        self, catalog: CurriculumCatalog
    ):
        phase0 = catalog.phases_by_slug["phase0"]
        topic = phase0.topics[0]
        assert catalog.topics_by_uuid[topic.uuid] is topic
        assert catalog.topics_by_phase_and_slug[(phase0.slug, topic.slug)] is topic

    def test_step_lookup_by_uuid_and_phase(self, catalog: CurriculumCatalog):
        phase0 = catalog.phases_by_slug["phase0"]
        topic = phase0.topics[0]
        step = topic.learning_steps[0]
        assert catalog.steps_by_uuid[step.uuid] is step
        assert step in catalog.steps_by_phase_slug[phase0.slug]
        assert catalog.topic_by_step_uuid[step.uuid] is topic
        assert catalog.phase_order_by_step_uuid[step.uuid] == phase0.order

    def test_requirement_lookup_by_uuid_slug_and_phase(
        self, catalog: CurriculumCatalog
    ):
        phase = next(p for p in catalog.phases if p.hands_on_verification)
        req = phase.hands_on_verification.requirements[0]
        assert catalog.requirements_by_uuid[req.uuid] is req
        assert catalog.requirements_by_slug[req.slug] is req
        assert req in catalog.requirements_by_phase_slug[phase.slug]
        assert catalog.phase_order_by_requirement_uuid[req.uuid] == phase.order

    def test_active_uuid_sets_and_counts(self, catalog: CurriculumCatalog):
        assert catalog.phase_count == len(catalog.phases)
        assert catalog.topic_count == len(catalog.active_topic_uuids)
        assert catalog.step_count == len(catalog.active_step_uuids)
        assert catalog.requirement_count == len(catalog.active_requirement_uuids)
        assert all(p.uuid in catalog.active_phase_uuids for p in catalog.phases)


class TestCurriculumCatalogImmutability:
    @pytest.fixture
    def catalog(self, real_payload: dict) -> CurriculumCatalog:
        with _patched_resource(json.dumps(real_payload)):
            return load_curriculum_catalog()

    @pytest.mark.parametrize(
        "attr",
        [
            "phases_by_slug",
            "phases_by_order",
            "topics_by_uuid",
            "topics_by_phase_and_slug",
            "steps_by_uuid",
            "steps_by_phase_slug",
            "topic_by_step_uuid",
            "phase_order_by_step_uuid",
            "requirements_by_uuid",
            "requirements_by_slug",
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
        clear_catalog_cache()
        second = get_curriculum_catalog()
        assert first is not second
        assert first == second
