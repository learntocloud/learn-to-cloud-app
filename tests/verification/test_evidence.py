"""Tests for the evidence cap."""

import pytest

from learn_to_cloud.verification.evidence import EvidenceError, apply_evidence_cap
from learn_to_cloud.verification.tasks.base import (
    EvidencePolicy,
    EvidenceSource,
    LLMRubricGraderConfig,
    VerificationTask,
)


def _task(
    *,
    source: EvidenceSource = "submitted_text",
    max_files: int = 10,
    max_file_size_bytes: int = 50 * 1024,
    max_total_bytes: int = 200 * 1024,
) -> VerificationTask:
    return VerificationTask(
        id="task-1",
        phase_id=3,
        name="Test task",
        evidence=EvidencePolicy(
            source=source,
            optional_files=[
                "a",
                "b",
                "c",
                "a.txt",
                "b.txt",
                "big.txt",
                "submission.txt",
                "present.txt",
                "second.txt",
            ],
            max_files=max_files,
            max_file_size_bytes=max_file_size_bytes,
            max_total_bytes=max_total_bytes,
        ),
        grader=LLMRubricGraderConfig(
            rubric_id="test", prompt_version="test", passing_score=0.5
        ),
    )


def test_apply_evidence_cap_rejects_duplicate_paths():
    with pytest.raises(EvidenceError, match="evidence.selection"):
        apply_evidence_cap(
            _task(),
            [("a.txt", "one"), ("a.txt", "two"), ("b.txt", "three")],
        )


def test_apply_evidence_cap_rejects_large_file():
    with pytest.raises(EvidenceError, match="evidence.item_limit"):
        apply_evidence_cap(_task(max_file_size_bytes=100), [("big.txt", "x" * 500)])


def test_apply_evidence_cap_rejects_too_many_files():
    with pytest.raises(EvidenceError, match="evidence.file_limit"):
        apply_evidence_cap(
            _task(max_files=1), [("present.txt", "here"), ("second.txt", "also")]
        )


def test_apply_evidence_cap_rejects_total_over_budget():
    with pytest.raises(EvidenceError, match="evidence.total_limit"):
        apply_evidence_cap(
            _task(max_total_bytes=5), [("a.txt", "four"), ("b.txt", "four")]
        )


@pytest.mark.parametrize("code", ["evidence.changed", "retrieval", "other"])
def test_unknown_evidence_codes_are_rejected(code):
    with pytest.raises(ValueError, match="Unknown evidence reason"):
        EvidenceError(code)
