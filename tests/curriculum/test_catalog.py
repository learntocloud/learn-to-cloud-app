"""Unit tests for the curriculum catalog (process-level artifact reader).

Covers:
- Catalog lookup indices
- Loading the real packaged artifact end to end
- Schema compatibility (artifact_schema_version mismatch fails fast)
- Strict failure on a missing/corrupted/tampered artifact
"""

from __future__ import annotations

import json
from copy import deepcopy
from unittest.mock import patch

import pytest

from learn_to_cloud.curriculum.catalog import (
    CurriculumCatalog,
    CurriculumCatalogError,
    get_curriculum_catalog,
    load_curriculum_catalog,
)
from learn_to_cloud.curriculum.compiler import (
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
        "learn_to_cloud.curriculum.catalog.files",
        autospec=True,
        return_value=_FakeResource(text),
    )


class TestLoadCurriculumCatalog:
    def test_loads_real_packaged_artifact(self):
        """The artifact actually committed to the wheel loads cleanly."""
        catalog = load_curriculum_catalog()
        assert catalog.phases
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

    def test_representative_indices_link_phase_topic_step_and_requirement(
        self, catalog: CurriculumCatalog
    ):
        phase = next(p for p in catalog.phases if p.topics and p.hands_on_verification)
        topic = next(t for t in phase.topics if t.learning_steps)
        step = topic.learning_steps[0]
        assert catalog.phases_by_slug[phase.slug] is phase
        assert catalog.steps_by_uuid[step.uuid] is step
        assert catalog.topic_by_step_uuid[step.uuid] is topic
        assert phase.hands_on_verification is not None
        requirement = phase.hands_on_verification.requirements[0]
        assert catalog.requirements_by_uuid[requirement.uuid] is requirement
        assert catalog.phase_order_by_requirement_uuid[requirement.uuid] == phase.order


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
            setattr(catalog, "curriculum_version", 999)
