"""Tests for the Phase 7 career reflection verification helpers."""

import pytest

from learn_to_cloud_shared.verification.career_reflection import (
    collect_career_reflection_evidence,
    validate_career_reflection,
)
from learn_to_cloud_shared.verification.evidence import EvidenceError
from learn_to_cloud_shared.verification.tasks import CAREER_REFLECTION_RUBRIC_TASK


@pytest.mark.unit
def test_validate_passes_for_non_empty_text():
    result = validate_career_reflection("A thoughtful reflection answer.")

    assert result.is_valid is True
    assert result.verification_completed is True


@pytest.mark.unit
@pytest.mark.parametrize("text", ["", "   ", "\n\t"])
def test_validate_fails_for_empty_text(text: str):
    result = validate_career_reflection(text)

    assert result.is_valid is False


@pytest.mark.unit
def test_collect_evidence_wraps_submitted_text():
    text = "## Question 0?\n\nMy answer goes here."

    bundle = collect_career_reflection_evidence(text, CAREER_REFLECTION_RUBRIC_TASK)

    assert bundle.source == "submitted_text"
    assert len(bundle.items) == 1
    assert bundle.items[0].content == text
    assert bundle.items[0].truncated is False
    assert bundle.total_bytes == len(text.encode("utf-8"))


@pytest.mark.unit
def test_collect_evidence_rejects_oversized_text():
    text = "x" * (CAREER_REFLECTION_RUBRIC_TASK.evidence.max_file_size_bytes + 500)

    with pytest.raises(EvidenceError, match="evidence.item_limit"):
        collect_career_reflection_evidence(text, CAREER_REFLECTION_RUBRIC_TASK)
