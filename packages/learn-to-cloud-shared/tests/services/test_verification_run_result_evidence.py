"""Evidence and prompt stripping before verification finalization."""

from __future__ import annotations

from uuid import uuid4

import pytest
from learn_to_cloud_shared_test_support.requirement_factories import (
    repo_fork_requirement,
)

from learn_to_cloud_shared.schemas import ValidationResult
from learn_to_cloud_shared.submission_values import submitted_value_from_raw
from learn_to_cloud_shared.verification.tasks.base import EvidenceBundle
from learn_to_cloud_shared.verification_workflow import (
    GradingDisposition,
    PreparedVerificationAttempt,
    VerificationRunResult,
    outcome_for_validation,
)


def _run_result(evidence) -> VerificationRunResult:
    requirement = repo_fork_requirement(required_repo="owner/repo")
    return VerificationRunResult(
        attempt=PreparedVerificationAttempt(
            id=uuid4(),
            user_id=1,
            github_username="alice",
            requirement=requirement,
            submitted_value=submitted_value_from_raw(
                requirement, "https://github.com/alice/repo"
            ),
        ),
        validation_result=ValidationResult(is_valid=True, message="ok"),
        evidence=evidence,
    )


@pytest.mark.unit
class TestVerificationRunResultEvidence:
    @pytest.mark.parametrize("is_valid", [False, True])
    def test_incomplete_result_never_counts_as_completed(self, is_valid) -> None:
        assert (
            outcome_for_validation(
                ValidationResult(
                    is_valid=is_valid,
                    verification_completed=False,
                    message="Verification did not finish.",
                    error_code="evidence.selection",
                )
            )
            == "server_error"
        )

    def test_evidence_error_survives_stripping(self) -> None:
        result = VerificationRunResult(
            attempt=_run_result(None).attempt,
            validation_result=ValidationResult(
                is_valid=False,
                message="Evidence could not be assembled.",
                verification_completed=False,
                error_code="evidence.total_limit",
            ),
            evidence=[EvidenceBundle(task_id="t1", source="repo_files")],
            grading_requests=[],
        )

        stripped = result.without_transport_data()

        assert stripped.validation_result.error_code == "evidence.total_limit"
        assert stripped.validation_result.verification_completed is False
        assert stripped.evidence is None
        assert stripped.grading_requests is None

    def test_defaults_to_none(self) -> None:
        result = VerificationRunResult(
            attempt=_run_result(None).attempt,
            validation_result=ValidationResult(is_valid=True, message="ok"),
        )
        assert result.evidence is None

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
    from tests.fakes.legacy_devops import (
        DEVOPS_IMPLEMENTATION_RUBRIC_TASK,
    )

    return LLMGradingRequest(
        task=DEVOPS_IMPLEMENTATION_RUBRIC_TASK,
        message="grade this",
    )


@pytest.mark.unit
class TestVerificationRunResultGradingRequests:
    def test_defaults_to_none(self) -> None:
        assert _run_result(None).grading_requests is None

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
