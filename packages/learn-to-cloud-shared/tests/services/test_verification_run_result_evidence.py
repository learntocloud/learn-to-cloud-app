"""Round-trip and strip tests for VerificationRunResult.evidence carrier."""

from __future__ import annotations

from uuid import uuid4

import pytest

from learn_to_cloud_shared.schemas import ValidationResult
from learn_to_cloud_shared.submission_values import SubmittedValue
from learn_to_cloud_shared.testing.requirement_factories import (
    repo_fork_requirement,
)
from learn_to_cloud_shared.verification.tasks.base import (
    EvidenceBundle,
    EvidenceItem,
)
from learn_to_cloud_shared.verification_workflow import (
    GradingDisposition,
    PreparedVerificationAttempt,
    VerificationRunResult,
)


def _run_result(evidence) -> VerificationRunResult:
    requirement = repo_fork_requirement(required_repo="owner/repo")
    return VerificationRunResult(
        attempt=PreparedVerificationAttempt(
            id=uuid4(),
            user_id=1,
            github_username="alice",
            requirement=requirement,
            submitted_value=SubmittedValue.from_raw(
                requirement, "https://github.com/alice/repo"
            ),
        ),
        validation_result=ValidationResult(is_valid=True, message="ok"),
        evidence=evidence,
    )


@pytest.mark.unit
class TestVerificationRunResultEvidence:
    def test_defaults_to_none(self) -> None:
        result = VerificationRunResult(
            attempt=_run_result(None).attempt,
            validation_result=ValidationResult(is_valid=True, message="ok"),
        )
        assert result.evidence is None

    def test_none_evidence_round_trips(self) -> None:
        restored = VerificationRunResult.from_payload(_run_result(None).to_payload())
        assert restored.evidence is None

    def test_evidence_round_trips(self) -> None:
        bundle = EvidenceBundle(
            task_id="t1",
            source="repo_files",
            items=[EvidenceItem(path="a.txt", content="hi", sha256="abc")],
            total_bytes=2,
        )
        restored = VerificationRunResult.from_payload(
            _run_result([bundle]).to_payload()
        )
        assert restored.evidence == [bundle]

    def test_without_transport_data_strips_bundles(self) -> None:
        bundle = EvidenceBundle(task_id="t1", source="repo_files")
        stripped = _run_result([bundle]).without_transport_data()
        assert stripped.evidence is None
        assert stripped.validation_result.is_valid is True

    def test_without_transport_data_is_noop_when_already_none(self) -> None:
        result = _run_result(None)
        assert result.without_transport_data() is result


def _grading_request():
    from learn_to_cloud_shared.verification.grading_requests import LLMGradingRequest
    from learn_to_cloud_shared.verification.tasks.phase3 import (
        JOURNAL_API_FINAL_RUBRIC_TASK,
    )

    return LLMGradingRequest(
        task=JOURNAL_API_FINAL_RUBRIC_TASK,
        message="grade this",
        thread_id="job-task",
    )


@pytest.mark.unit
class TestVerificationRunResultGradingRequests:
    def test_defaults_to_none(self) -> None:
        assert _run_result(None).grading_requests is None

    def test_none_grading_requests_round_trips(self) -> None:
        restored = VerificationRunResult.from_payload(_run_result(None).to_payload())
        assert restored.grading_requests is None

    def test_grading_requests_round_trip(self) -> None:
        request = _grading_request()
        result = VerificationRunResult(
            attempt=_run_result(None).attempt,
            validation_result=ValidationResult(is_valid=True, message="ok"),
            grading_requests=[request],
        )
        restored = VerificationRunResult.from_payload(result.to_payload())
        assert restored.grading_requests == [request]

    def test_empty_grading_requests_round_trip(self) -> None:
        result = VerificationRunResult(
            attempt=_run_result(None).attempt,
            validation_result=ValidationResult(is_valid=False, message="gate failed"),
            grading_requests=[],
            grading_disposition=GradingDisposition.SKIPPED_GATE_FAILED,
        )
        restored = VerificationRunResult.from_payload(result.to_payload())
        assert restored.grading_requests == []
        assert restored.grading_disposition == GradingDisposition.SKIPPED_GATE_FAILED

    def test_without_transport_data_strips_grading_requests(self) -> None:
        result = VerificationRunResult(
            attempt=_run_result(None).attempt,
            validation_result=ValidationResult(is_valid=True, message="ok"),
            grading_requests=[_grading_request()],
            grading_disposition=GradingDisposition.REQUESTED,
        )
        stripped = result.without_transport_data()
        assert stripped.grading_requests is None
        assert stripped.grading_disposition == GradingDisposition.REQUESTED
