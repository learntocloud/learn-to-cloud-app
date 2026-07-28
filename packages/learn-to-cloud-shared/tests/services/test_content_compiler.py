"""Unit tests for the deterministic curriculum artifact compiler.

Covers:
- Compiler determinism (same YAML in -> byte-identical artifact out)
- content_hash correctness (recomputes over the canonical payload)
- Strict failure on missing/malformed/inconsistent content (fails
  instead of skipping, unlike the tolerant YAML loader)
- curriculum_version policy checks (unchanged/decrease/bump)
- Compiling the real authored curriculum cleanly
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest
import yaml

from learn_to_cloud_shared.content_compiler import (
    ARTIFACT_SCHEMA_VERSION,
    ContentCompileError,
    compile_and_write,
    compile_curriculum_artifact,
    compute_content_hash,
    render_artifact_file,
)
from learn_to_cloud_shared.content_yaml_loader import ContentValidationError

pytestmark = pytest.mark.unit


def _patched_content_dir(phases_dir: Path):
    """Patch the content_yaml_loader's private content dir resolver."""
    return patch(
        "learn_to_cloud_shared.content_yaml_loader._get_content_dir",
        autospec=True,
        return_value=phases_dir,
    )


def _write_meta(content_root: Path, *, curriculum_version: object = 1) -> None:
    (content_root / "curriculum.meta.yaml").write_text(
        yaml.safe_dump({"curriculum_version": curriculum_version})
    )


def _write_minimal_phase(
    phases_dir: Path,
    *,
    phase_uuid: str = "11111111-1111-1111-1111-111111111111",
    order: int = 0,
    topic_uuid: str = "22222222-2222-2222-2222-222222222222",
    step_uuid: str = "33333333-3333-3333-3333-333333333333",
    topic_slug: str = "basics",
) -> None:
    """Write a single-phase, single-topic, single-step content tree."""
    phase_dir = phases_dir / "phase0"
    phase_dir.mkdir(parents=True, exist_ok=True)
    (phase_dir / "_phase.yaml").write_text(
        yaml.safe_dump(
            {
                "uuid": phase_uuid,
                "name": "Phase Zero",
                "order": order,
                "topics": [topic_slug],
            }
        )
    )
    (phase_dir / f"{topic_slug}.yaml").write_text(
        yaml.safe_dump(
            {
                "uuid": topic_uuid,
                "slug": topic_slug,
                "name": "Basics",
                "description": "Learn the basics",
                "learning_steps": [
                    {
                        "uuid": step_uuid,
                        "slug": "step-1",
                        "order": 1,
                        "title": "First step",
                    }
                ],
            }
        )
    )


@pytest.fixture
def minimal_content_root(tmp_path: Path) -> Path:
    """A tmp content/ root with phases/ + curriculum.meta.yaml, patched in."""
    phases_dir = tmp_path / "phases"
    phases_dir.mkdir()
    _write_minimal_phase(phases_dir)
    _write_meta(tmp_path)
    return tmp_path


class TestCompileCurriculumArtifact:
    def test_compiles_minimal_curriculum(self, minimal_content_root: Path):
        with _patched_content_dir(minimal_content_root / "phases"):
            payload = compile_curriculum_artifact()

        assert payload["artifact_schema_version"] == ARTIFACT_SCHEMA_VERSION
        assert payload["curriculum_version"] == 1
        assert len(payload["phases"]) == 1
        assert payload["phases"][0]["slug"] == "phase0"
        assert isinstance(payload["content_hash"], str)
        assert len(payload["content_hash"]) == 64  # sha256 hex digest

    def test_determinism_across_repeated_compiles(self, minimal_content_root: Path):
        with _patched_content_dir(minimal_content_root / "phases"):
            first = compile_curriculum_artifact()
            second = compile_curriculum_artifact()

        assert render_artifact_file(first) == render_artifact_file(second)
        assert first == second

    def test_content_hash_matches_recomputation(self, minimal_content_root: Path):
        with _patched_content_dir(minimal_content_root / "phases"):
            payload = compile_curriculum_artifact()

        without_hash = {k: v for k, v in payload.items() if k != "content_hash"}
        assert payload["content_hash"] == compute_content_hash(without_hash)

    def test_array_order_is_meaningful_not_sorted(self, tmp_path: Path):
        """Phases keep declared order, not e.g. alphabetical-by-uuid order."""
        phases_dir = tmp_path / "phases"
        phases_dir.mkdir()
        for slug, order, phase_uuid in [
            ("phase1", 1, "22222222-2222-2222-2222-222222222222"),
            ("phase0", 0, "11111111-1111-1111-1111-111111111111"),
        ]:
            phase_dir = phases_dir / slug
            phase_dir.mkdir()
            (phase_dir / "_phase.yaml").write_text(
                yaml.safe_dump({"uuid": phase_uuid, "name": slug, "order": order})
            )
        _write_meta(tmp_path)

        with _patched_content_dir(phases_dir):
            payload = compile_curriculum_artifact()

        assert [p["slug"] for p in payload["phases"]] == ["phase0", "phase1"]

    def test_real_authored_curriculum_compiles_cleanly(self):
        """The actual repo content must compile without errors end to end."""
        payload = compile_curriculum_artifact()
        assert payload["artifact_schema_version"] == ARTIFACT_SCHEMA_VERSION
        assert len(payload["phases"]) > 0


class TestStrictFailure:
    def test_missing_curriculum_meta_raises(self, tmp_path: Path):
        phases_dir = tmp_path / "phases"
        phases_dir.mkdir()
        _write_minimal_phase(phases_dir)
        # No curriculum.meta.yaml written.

        with (
            _patched_content_dir(phases_dir),
            pytest.raises(ContentCompileError, match="missing curriculum metadata"),
        ):
            compile_curriculum_artifact()

    def test_non_integer_curriculum_version_raises(self, tmp_path: Path):
        phases_dir = tmp_path / "phases"
        phases_dir.mkdir()
        _write_minimal_phase(phases_dir)
        _write_meta(tmp_path, curriculum_version="not-a-number")

        with (
            _patched_content_dir(phases_dir),
            pytest.raises(ContentCompileError, match="positive integer"),
        ):
            compile_curriculum_artifact()

    def test_non_positive_curriculum_version_raises(self, tmp_path: Path):
        phases_dir = tmp_path / "phases"
        phases_dir.mkdir()
        _write_minimal_phase(phases_dir)
        _write_meta(tmp_path, curriculum_version=0)

        with (
            _patched_content_dir(phases_dir),
            pytest.raises(ContentCompileError, match="positive integer"),
        ):
            compile_curriculum_artifact()

    def test_empty_curriculum_raises(self, tmp_path: Path):
        phases_dir = tmp_path / "phases"
        phases_dir.mkdir()
        _write_meta(tmp_path)

        with (
            _patched_content_dir(phases_dir),
            pytest.raises(ContentCompileError, match="no phases loaded"),
        ):
            compile_curriculum_artifact()

    def test_missing_topic_file_raises_instead_of_skipping(self, tmp_path: Path):
        """Unlike the tolerant loader, a dangling topic slug must fail loudly."""
        phases_dir = tmp_path / "phases"
        phase_dir = phases_dir / "phase0"
        phase_dir.mkdir(parents=True)
        (phase_dir / "_phase.yaml").write_text(
            yaml.safe_dump(
                {
                    "uuid": "11111111-1111-1111-1111-111111111111",
                    "name": "Phase Zero",
                    "order": 0,
                    "topics": ["missing-topic"],
                }
            )
        )
        _write_meta(tmp_path)

        with (
            _patched_content_dir(phases_dir),
            pytest.raises(ContentValidationError, match="missing topic file"),
        ):
            compile_curriculum_artifact()

    def test_malformed_yaml_raises(self, tmp_path: Path):
        phases_dir = tmp_path / "phases"
        phase_dir = phases_dir / "phase0"
        phase_dir.mkdir(parents=True)
        (phase_dir / "_phase.yaml").write_text("{not: valid: yaml: [")
        _write_meta(tmp_path)

        with (
            _patched_content_dir(phases_dir),
            pytest.raises(yaml.YAMLError),
        ):
            compile_curriculum_artifact()

    def test_duplicate_uuid_raises(self, tmp_path: Path):
        """Cross-file validation (uuid uniqueness) is reused, not duplicated."""
        phases_dir = tmp_path / "phases"
        shared_uuid = "11111111-1111-1111-1111-111111111111"
        _write_minimal_phase(phases_dir, phase_uuid=shared_uuid, topic_uuid=shared_uuid)
        _write_meta(tmp_path)

        with (
            _patched_content_dir(phases_dir),
            pytest.raises(ContentCompileError, match="Duplicate uuid"),
        ):
            compile_curriculum_artifact()

    def test_non_sequential_phase_order_raises(self, tmp_path: Path):
        phases_dir = tmp_path / "phases"
        phases_dir.mkdir()
        for slug, order, phase_uuid in [
            ("phase0", 0, "11111111-1111-1111-1111-111111111111"),
            ("phase1", 2, "22222222-2222-2222-2222-222222222222"),
        ]:
            phase_dir = phases_dir / slug
            phase_dir.mkdir()
            (phase_dir / "_phase.yaml").write_text(
                yaml.safe_dump({"uuid": phase_uuid, "name": slug, "order": order})
            )
        _write_meta(tmp_path)

        with (
            _patched_content_dir(phases_dir),
            pytest.raises(ContentCompileError, match="gapless"),
        ):
            compile_curriculum_artifact()


class TestVersionPolicy:
    def _compile(self, phases_dir: Path) -> dict:
        with _patched_content_dir(phases_dir):
            return compile_curriculum_artifact()

    def test_unchanged_payload_same_version_passes(
        self, minimal_content_root: Path, tmp_path: Path
    ):
        previous = tmp_path / "previous.json"
        previous.write_text(json.dumps(self._compile(minimal_content_root / "phases")))

        with _patched_content_dir(minimal_content_root / "phases"):
            payload = compile_curriculum_artifact(previous_artifact_path=previous)

        assert payload["curriculum_version"] == 1

    def test_changed_payload_same_version_raises(
        self, minimal_content_root: Path, tmp_path: Path
    ):
        previous_payload = self._compile(minimal_content_root / "phases")
        previous_payload["phases"][0]["name"] = "A Different Name"
        previous = tmp_path / "previous.json"
        previous.write_text(json.dumps(previous_payload))

        with (
            _patched_content_dir(minimal_content_root / "phases"),
            pytest.raises(ContentCompileError, match="was not bumped"),
        ):
            compile_curriculum_artifact(previous_artifact_path=previous)

    def test_version_decrease_raises(self, minimal_content_root: Path, tmp_path: Path):
        previous_payload = self._compile(minimal_content_root / "phases")
        previous_payload["curriculum_version"] = 5
        previous = tmp_path / "previous.json"
        previous.write_text(json.dumps(previous_payload))

        with (
            _patched_content_dir(minimal_content_root / "phases"),
            pytest.raises(ContentCompileError, match="must not decrease"),
        ):
            compile_curriculum_artifact(previous_artifact_path=previous)

    def test_changed_payload_higher_version_passes(self, tmp_path: Path):
        phases_dir = tmp_path / "phases"
        phases_dir.mkdir()
        _write_minimal_phase(phases_dir)
        _write_meta(tmp_path, curriculum_version=2)

        previous = tmp_path / "previous.json"
        previous.write_text(
            json.dumps(
                {
                    "artifact_schema_version": ARTIFACT_SCHEMA_VERSION,
                    "curriculum_version": 1,
                    "phases": [],
                    "content_hash": "irrelevant",
                }
            )
        )

        with _patched_content_dir(phases_dir):
            payload = compile_curriculum_artifact(previous_artifact_path=previous)

        assert payload["curriculum_version"] == 2

    def test_missing_previous_artifact_never_blocks(
        self, minimal_content_root: Path, tmp_path: Path
    ):
        previous = tmp_path / "does-not-exist.json"

        with _patched_content_dir(minimal_content_root / "phases"):
            payload = compile_curriculum_artifact(previous_artifact_path=previous)

        assert payload["curriculum_version"] == 1


class TestCompileAndWrite:
    def test_writes_file_and_is_idempotent(self, minimal_content_root: Path):
        with _patched_content_dir(minimal_content_root / "phases"):
            path1 = compile_and_write()
            contents1 = path1.read_text()
            path2 = compile_and_write()
            contents2 = path2.read_text()

        assert path1 == path2
        assert contents1 == contents2
        assert contents1.endswith("\n")

    def test_writes_to_explicit_output_path(
        self, minimal_content_root: Path, tmp_path: Path
    ):
        target = tmp_path / "out" / "curriculum.json"
        target.parent.mkdir()

        with _patched_content_dir(minimal_content_root / "phases"):
            written = compile_and_write(target)

        assert written == target
        assert json.loads(target.read_text())["artifact_schema_version"] == (
            ARTIFACT_SCHEMA_VERSION
        )
