"""Unit tests for content_yaml_loader.

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

from learn_to_cloud_shared.content_yaml_loader import (
    ContentValidationError,
    _load_phase,
    _load_topic,
    _validate_topic_payload,
    clear_cache,
)
from learn_to_cloud_shared.content_yaml_loader import (
    get_all_phases_from_yaml as get_all_phases,
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
        assert _load_topic(tmp_path, "nonexistent", order=1) is None

    def test_valid_yaml_returns_topic(self, tmp_path: Path):
        topic_file = tmp_path / "basics.yaml"
        topic_file.write_text(
            """
uuid: 00000000-0000-0000-0000-000000000001
id: phase0-topic1
slug: basics
name: Basics
description: Learn the basics
learning_steps:
  - uuid: 00000000-0000-0000-0000-000000000002
    id: step-intro
    order: 0
    title: Introduction
"""
        )
        topic = _load_topic(tmp_path, "basics", order=1)
        assert topic is not None
        assert topic.id == "phase0-topic1"
        assert topic.order == 1  # supplied by caller, not from YAML
        assert len(topic.learning_steps) == 1

    def test_invalid_yaml_returns_none(self, tmp_path: Path):
        topic_file = tmp_path / "bad.yaml"
        topic_file.write_text("{invalid yaml: [")
        assert _load_topic(tmp_path, "bad", order=1) is None

    def test_topic_with_order_field_is_rejected(self, tmp_path: Path):
        """``order`` in topic YAML must be removed -- it's derived from
        the slug list position in _phase.yaml (issue #463)."""
        topic_file = tmp_path / "withorder.yaml"
        topic_file.write_text(
            """
uuid: 00000000-0000-0000-0000-000000000099
id: phase0-topic99
slug: withorder
name: With Order
description: Has a stale order field
order: 5
learning_steps:
  - uuid: 00000000-0000-0000-0000-0000000000aa
    id: s
    order: 0
    title: T
"""
        )
        assert _load_topic(tmp_path, "withorder", order=1) is None

    def test_validation_failure_returns_none(self, tmp_path: Path):
        topic_file = tmp_path / "dup.yaml"
        topic_file.write_text(
            """
uuid: 00000000-0000-0000-0000-000000000010
id: topic-dup
slug: dup
name: Dup
description: duplicate steps
learning_steps:
  - uuid: 00000000-0000-0000-0000-000000000011
    id: same-id
    order: 0
    title: A
  - uuid: 00000000-0000-0000-0000-000000000012
    id: same-id
    order: 1
    title: B
"""
        )
        assert _load_topic(tmp_path, "dup", order=1) is None


# ---------------------------------------------------------------------------
# _load_phase
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestLoadPhase:
    def test_missing_meta_file_returns_none(self, tmp_path: Path):
        with patch(
            "learn_to_cloud_shared.content_yaml_loader._get_content_dir",
            autospec=True,
            return_value=tmp_path,
        ):
            assert _load_phase("phase99") is None

    def test_valid_phase_loads(self, tmp_path: Path):
        phase_dir = tmp_path / "phase0"
        phase_dir.mkdir()
        (phase_dir / "_phase.yaml").write_text(
            """
uuid: 00000000-0000-0000-0000-000000000100
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
uuid: 00000000-0000-0000-0000-000000000101
id: phase0-basics
slug: basics
name: Basics
description: desc
learning_steps:
  - uuid: 00000000-0000-0000-0000-000000000102
    id: step-1
    order: 0
    title: First step
"""
        )
        with patch(
            "learn_to_cloud_shared.content_yaml_loader._get_content_dir",
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
    def test_packaged_content_contains_journal_requirement(self):
        requirements = [
            requirement
            for phase in get_all_phases()
            if phase.hands_on_verification
            for requirement in phase.hands_on_verification.requirements
        ]

        assert any(req.id == "journal-api-implementation" for req in requirements)

    def test_phase3_exposes_single_final_journal_verification(self):
        phase3 = next(phase for phase in get_all_phases() if phase.id == 3)

        assert phase3.hands_on_verification is not None
        assert [
            requirement.id for requirement in phase3.hands_on_verification.requirements
        ] == ["journal-api-implementation"]

    def test_phase5_aws_observability_link_uses_current_adot_guide(self):
        phase5 = next(phase for phase in get_all_phases() if phase.slug == "phase5")
        topic = next(t for t in phase5.topics if t.slug == "monitoring-observability")
        step = next(
            step
            for step in topic.learning_steps
            if step.id == "phase5-topic5-practice-export-telemetry-cloud-provider"
        )
        aws_option = next(option for option in step.options if option.provider == "aws")

        assert aws_option.url == "https://aws-otel.github.io/docs/getting-started/x-ray"

    def test_empty_directory(self, tmp_path: Path):
        with patch(
            "learn_to_cloud_shared.content_yaml_loader._get_content_dir",
            autospec=True,
            return_value=tmp_path,
        ):
            assert get_all_phases() == ()

    def test_nonexistent_directory(self, tmp_path: Path):
        with patch(
            "learn_to_cloud_shared.content_yaml_loader._get_content_dir",
            autospec=True,
            return_value=tmp_path / "nonexistent",
        ):
            assert get_all_phases() == ()

    def test_ignores_non_phase_dirs(self, tmp_path: Path):
        (tmp_path / "README.md").touch()
        (tmp_path / "not-a-phase").mkdir()
        with patch(
            "learn_to_cloud_shared.content_yaml_loader._get_content_dir",
            autospec=True,
            return_value=tmp_path,
        ):
            assert get_all_phases() == ()


# ---------------------------------------------------------------------------
# Lookup-by-walking helpers used to live in this module. Phase C (#464)
# moved them to the DB loader, where ``test_content_db_loader.py`` exercises
# the same behavior against real curriculum tables.
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# validate_content (cross-file validators -- issue #462)
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestValidateContent:
    def _build_phase(
        self,
        *,
        slug: str = "phase0",
        phase_uuid: str = "00000000-0000-0000-0000-000000000001",
        topics: list | None = None,
        topic_slugs: list[str] | None = None,
        requirements: list | None = None,
    ):
        from uuid import UUID

        from learn_to_cloud_shared.schemas import (
            Phase,
            PhaseHandsOnVerificationOverview,
        )

        return Phase(
            uuid=UUID(phase_uuid),
            id=0,
            name=slug,
            slug=slug,
            order=0,
            topics=topics or [],
            topic_slugs=topic_slugs or [],
            hands_on_verification=(
                PhaseHandsOnVerificationOverview(requirements=requirements)
                if requirements is not None
                else None
            ),
        )

    def _build_topic(
        self,
        *,
        slug: str = "topic1",
        topic_uuid: str = "00000000-0000-0000-0000-000000000010",
        learning_steps: list | None = None,
    ):
        from uuid import UUID

        from learn_to_cloud_shared.schemas import LearningStep, Topic

        return Topic(
            uuid=UUID(topic_uuid),
            id=slug,
            slug=slug,
            name=slug,
            description="",
            order=0,
            learning_steps=learning_steps
            or [
                LearningStep(
                    uuid=UUID("00000000-0000-0000-0000-000000000020"),
                    id="step-1",
                    order=0,
                ),
            ],
        )

    def test_returns_empty_list_when_no_violations(self):
        from learn_to_cloud_shared.content_yaml_loader import validate_content

        phase = self._build_phase(topics=[self._build_topic()], topic_slugs=["topic1"])
        with patch(
            "learn_to_cloud_shared.content_yaml_loader.get_all_phases_from_yaml",
            autospec=True,
            return_value=(phase,),
        ):
            assert validate_content() == []

    def test_detects_duplicate_uuid_across_entities(self):
        from uuid import UUID

        from learn_to_cloud_shared.content_yaml_loader import validate_content
        from learn_to_cloud_shared.schemas import LearningStep

        # Same UUID used for a topic and one of its steps.
        shared = "00000000-0000-0000-0000-deadbeef0001"
        topic = self._build_topic(
            topic_uuid=shared,
            learning_steps=[
                LearningStep(uuid=UUID(shared), id="step-1", order=0),
            ],
        )
        phase = self._build_phase(topics=[topic], topic_slugs=["topic1"])
        with patch(
            "learn_to_cloud_shared.content_yaml_loader.get_all_phases_from_yaml",
            autospec=True,
            return_value=(phase,),
        ):
            errors = validate_content()
        assert any("Duplicate uuid" in e for e in errors)

    def test_detects_topic_slug_count_mismatch(self):
        from learn_to_cloud_shared.content_yaml_loader import validate_content

        # phase declares two topics in YAML but only one loaded.
        phase = self._build_phase(
            topics=[self._build_topic()],
            topic_slugs=["topic1", "missing-topic"],
        )
        with patch(
            "learn_to_cloud_shared.content_yaml_loader.get_all_phases_from_yaml",
            autospec=True,
            return_value=(phase,),
        ):
            errors = validate_content()
        assert any("expected 2 topics" in e for e in errors)

    def test_detects_duplicate_step_order_within_topic(self):
        from uuid import UUID

        from learn_to_cloud_shared.content_yaml_loader import validate_content
        from learn_to_cloud_shared.schemas import LearningStep

        topic = self._build_topic(
            learning_steps=[
                LearningStep(
                    uuid=UUID("00000000-0000-0000-0000-000000000030"),
                    id="step-a",
                    order=1,
                ),
                LearningStep(
                    uuid=UUID("00000000-0000-0000-0000-000000000031"),
                    id="step-b",
                    order=1,
                ),
            ],
        )
        phase = self._build_phase(topics=[topic], topic_slugs=["topic1"])
        with patch(
            "learn_to_cloud_shared.content_yaml_loader.get_all_phases_from_yaml",
            autospec=True,
            return_value=(phase,),
        ):
            errors = validate_content()
        assert any("order=1" in e for e in errors)
