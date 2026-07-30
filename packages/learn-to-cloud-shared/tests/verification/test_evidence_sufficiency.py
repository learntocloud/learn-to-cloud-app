"""Tests for deterministic evidence-sufficiency signals."""

from __future__ import annotations

import pytest

from learn_to_cloud_shared.verification.evidence import apply_evidence_cap
from learn_to_cloud_shared.verification.tasks.base import (
    EvidencePolicy,
    LLMRubricGraderConfig,
    VerificationTask,
)


def _task(**policy_overrides: object) -> VerificationTask:
    policy_args: dict[str, object] = {
        "source": "repo_files",
        "max_files": 5,
        "max_file_size_bytes": 100,
        "max_total_bytes": 500,
    }
    policy_args.update(policy_overrides)
    return VerificationTask(
        id="test-task",
        phase_id=4,
        name="Test Task",
        evidence=EvidencePolicy(**policy_args),  # type: ignore[arg-type]
        grader=LLMRubricGraderConfig(
            rubric_id="test-v1",
            prompt_id="phase4-deployment-architecture",
            passing_score=0.7,
        ),
    )


def test_complete_evidence_is_sufficient() -> None:
    bundle = apply_evidence_cap(_task(), [("deploy.sh", "echo hi")])

    assert bundle.is_sufficient
    assert bundle.sufficiency_warnings == []


def test_truncated_file_is_flagged() -> None:
    bundle = apply_evidence_cap(_task(), [("deploy.sh", "x" * 500)])

    assert bundle.truncated_paths == ["deploy.sh"]
    assert not bundle.is_sufficient
    assert "Truncated" in bundle.sufficiency_warnings[0]


def test_missing_optional_path_does_not_warn() -> None:
    """Tasks request alternatives like ci.yml/ci.yaml; one is always absent."""
    bundle = apply_evidence_cap(
        _task(),
        [("ci.yml", "on: push")],
        missing_paths=["ci.yaml"],
    )

    assert bundle.missing_paths == ["ci.yaml"]
    assert bundle.missing_required_paths == []
    assert bundle.is_sufficient


def test_missing_required_path_warns() -> None:
    bundle = apply_evidence_cap(
        _task(required_files=["deploy.sh"]),
        [],
        missing_paths=["deploy.sh"],
    )

    assert bundle.missing_required_paths == ["deploy.sh"]
    assert not bundle.is_sufficient
    assert "deploy.sh" in bundle.sufficiency_warnings[0]


def test_file_dropped_by_total_cap_is_recorded() -> None:
    bundle = apply_evidence_cap(
        _task(max_file_size_bytes=100, max_total_bytes=120),
        [("a.sh", "a" * 90), ("b.sh", "b" * 90)],
    )

    assert [item.path for item in bundle.items] == ["a.sh"]
    assert bundle.dropped_paths == ["b.sh"]
    assert not bundle.is_sufficient


def test_oversized_file_no_longer_discards_later_files() -> None:
    """A file that does not fit must not silently end collection."""
    bundle = apply_evidence_cap(
        _task(max_file_size_bytes=100, max_total_bytes=120),
        [("big.sh", "b" * 100), ("small.sh", "s")],
    )

    assert [item.path for item in bundle.items] == ["big.sh", "small.sh"]


def test_file_dropped_by_count_cap_is_recorded() -> None:
    bundle = apply_evidence_cap(
        _task(max_files=1),
        [("a.sh", "a"), ("b.sh", "b")],
    )

    assert bundle.dropped_paths == ["b.sh"]


@pytest.mark.parametrize("warning_source", ["truncated", "dropped", "missing"])
def test_any_warning_makes_bundle_insufficient(warning_source: str) -> None:
    if warning_source == "truncated":
        bundle = apply_evidence_cap(_task(), [("a.sh", "x" * 500)])
    elif warning_source == "dropped":
        bundle = apply_evidence_cap(_task(max_files=1), [("a.sh", "a"), ("b.sh", "b")])
    else:
        bundle = apply_evidence_cap(
            _task(required_files=["a.sh"]), [], missing_paths=["a.sh"]
        )

    assert not bundle.is_sufficient
