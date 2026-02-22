"""Unit tests for content_service.

Tests cover:
- _validate_topic_payload step ID validation rules
- _load_topic YAML loading and error handling
- _load_phase directory-based phase loading
- get_all_phases discovery and sorting
- get_phase_by_slug / get_topic_by_id / get_topic_by_slugs lookups
- clear_cache invalidation
"""

from pathlib import Path
from unittest.mock import patch

import pytest

from services.content_service import (
    ContentValidationError,
    _load_phase,
    _load_topic,
    _validate_topic_payload,
    clear_cache,
    get_all_phases,
    get_phase_by_slug,
    get_topic_by_id,
    get_topic_by_slugs,
)


@pytest.fixture(autouse=True)
def _clear_content_cache():
    """Clear lru_cache between tests."""
    clear_cache()
    yield
    clear_cache()


# ---------------------------------------------------------------------------
# _validate_topic_payload
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestValidateTopicPayload:
    def test_valid_payload(self):
        data = {
            "id": "topic1",
            "learning_steps": [
                {"id": "step-1", "order": 1},
                {"id": "step-2", "order": 2},
            ],
        }
        _validate_topic_payload(data, Path("test.yaml"))

    def test_missing_step_id_raises(self):
        data = {
            "id": "topic1",
            "learning_steps": [{"order": 1}],
        }
        with pytest.raises(ContentValidationError, match="Missing learning_steps"):
            _validate_topic_payload(data, Path("test.yaml"))

    def test_empty_step_id_raises(self):
        data = {
            "id": "topic1",
            "learning_steps": [{"id": "", "order": 1}],
        }
        with pytest.raises(ContentValidationError, match="Missing learning_steps"):
            _validate_topic_payload(data, Path("test.yaml"))

    def test_duplicate_step_id_raises(self):
        data = {
            "id": "topic1",
            "learning_steps": [
                {"id": "step-1", "order": 1},
                {"id": "step-1", "order": 2},
            ],
        }
        with pytest.raises(ContentValidationError, match="Duplicate"):
            _validate_topic_payload(data, Path("test.yaml"))

    def test_oversized_step_id_raises(self):
        data = {
            "id": "topic1",
            "learning_steps": [{"id": "x" * 101, "order": 1}],
        }
        with pytest.raises(ContentValidationError, match="max 100"):
            _validate_topic_payload(data, Path("test.yaml"))

    def test_non_list_steps_raises(self):
        data = {"id": "topic1", "learning_steps": "not-a-list"}
        with pytest.raises(ContentValidationError, match="must be a list"):
            _validate_topic_payload(data, Path("test.yaml"))

    def test_non_dict_step_raises(self):
        data = {"id": "topic1", "learning_steps": ["not-a-dict"]}
        with pytest.raises(ContentValidationError, match="must be a mapping"):
            _validate_topic_payload(data, Path("test.yaml"))

    def test_uses_filename_stem_when_no_topic_id(self):
        data = {"learning_steps": [{"order": 1}]}
        with pytest.raises(ContentValidationError, match="test"):
            _validate_topic_payload(data, Path("test.yaml"))


# ---------------------------------------------------------------------------
# _load_topic
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestLoadTopic:
    def test_missing_file_returns_none(self, tmp_path: Path):
        assert _load_topic(tmp_path, "nonexistent") is None

    def test_valid_yaml_returns_topic(self, tmp_path: Path):
        topic_file = tmp_path / "basics.yaml"
        topic_file.write_text(
            """
id: phase0-topic1
slug: basics
name: Basics
description: Learn the basics
order: 0
learning_steps:
  - id: step-intro
    order: 0
    title: Introduction
"""
        )
        topic = _load_topic(tmp_path, "basics")
        assert topic is not None
        assert topic.id == "phase0-topic1"
        assert len(topic.learning_steps) == 1

    def test_invalid_yaml_returns_none(self, tmp_path: Path):
        topic_file = tmp_path / "bad.yaml"
        topic_file.write_text("{invalid yaml: [")
        assert _load_topic(tmp_path, "bad") is None

    def test_validation_failure_returns_none(self, tmp_path: Path):
        topic_file = tmp_path / "dup.yaml"
        topic_file.write_text(
            """
id: topic-dup
slug: dup
name: Dup
description: duplicate steps
order: 0
learning_steps:
  - id: same-id
    order: 0
    title: A
  - id: same-id
    order: 1
    title: B
"""
        )
        assert _load_topic(tmp_path, "dup") is None


# ---------------------------------------------------------------------------
# _load_phase
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestLoadPhase:
    def test_missing_meta_file_returns_none(self, tmp_path: Path):
        with patch(
            "services.content_service._get_content_dir",
            autospec=True,
            return_value=tmp_path,
        ):
            assert _load_phase("phase99") is None

    def test_valid_phase_loads(self, tmp_path: Path):
        phase_dir = tmp_path / "phase0"
        phase_dir.mkdir()
        (phase_dir / "_phase.yaml").write_text(
            """
id: 0
name: Foundation
slug: phase0
description: Foundation phase
order: 0
topics:
  - basics
"""
        )
        (phase_dir / "basics.yaml").write_text(
            """
id: phase0-basics
slug: basics
name: Basics
description: desc
order: 0
learning_steps:
  - id: step-1
    order: 0
    title: First step
"""
        )
        with patch(
            "services.content_service._get_content_dir",
            autospec=True,
            return_value=tmp_path,
        ):
            phase = _load_phase("phase0")
        assert phase is not None
        assert phase.id == 0
        assert len(phase.topics) == 1


# ---------------------------------------------------------------------------
# get_all_phases
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestGetAllPhases:
    def test_empty_directory(self, tmp_path: Path):
        with patch(
            "services.content_service._get_content_dir",
            autospec=True,
            return_value=tmp_path,
        ):
            assert get_all_phases() == ()

    def test_nonexistent_directory(self, tmp_path: Path):
        with patch(
            "services.content_service._get_content_dir",
            autospec=True,
            return_value=tmp_path / "nonexistent",
        ):
            assert get_all_phases() == ()

    def test_ignores_non_phase_dirs(self, tmp_path: Path):
        (tmp_path / "README.md").touch()
        (tmp_path / "not-a-phase").mkdir()
        with patch(
            "services.content_service._get_content_dir",
            autospec=True,
            return_value=tmp_path,
        ):
            assert get_all_phases() == ()


# ---------------------------------------------------------------------------
# Lookup functions
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestLookupFunctions:
    def test_get_phase_by_slug_found(self):
        from schemas import Phase

        phase = Phase(id=0, name="P0", slug="phase0", order=0, topics=[])
        with patch(
            "services.content_service.get_all_phases",
            autospec=True,
            return_value=(phase,),
        ):
            assert get_phase_by_slug("phase0") is phase

    def test_get_phase_by_slug_not_found(self):
        with patch(
            "services.content_service.get_all_phases",
            autospec=True,
            return_value=(),
        ):
            assert get_phase_by_slug("nonexistent") is None

    def test_get_topic_by_id_not_found(self):
        with patch(
            "services.content_service.get_all_phases",
            autospec=True,
            return_value=(),
        ):
            assert get_topic_by_id("nonexistent") is None

    def test_get_topic_by_slugs_phase_not_found(self):
        with patch(
            "services.content_service.get_all_phases",
            autospec=True,
            return_value=(),
        ):
            assert get_topic_by_slugs("nonexistent", "topic") is None
