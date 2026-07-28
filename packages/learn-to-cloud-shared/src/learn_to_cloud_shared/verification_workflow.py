"""Serializable types shared by verification workflow activities."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, replace
from enum import StrEnum
from uuid import UUID

from learn_to_cloud_shared.github_target import GitHubTarget
from learn_to_cloud_shared.schemas import (
    HandsOnRequirement,
    HandsOnRequirementAdapter,
    ValidationResult,
)
from learn_to_cloud_shared.submission_derivation import build_target
from learn_to_cloud_shared.submission_values import SubmittedValue
from learn_to_cloud_shared.verification.grading_requests import LLMGradingRequest
from learn_to_cloud_shared.verification.tasks.base import EvidenceBundle

VALIDATION_FAILED_ERROR_CODE = "validation_failed"
VERIFICATION_INCOMPLETE_ERROR_CODE = "verification_incomplete"
VERIFICATION_SUCCEEDED_CODE = "verification_succeeded"

OUTCOME_SUCCEEDED = "succeeded"
OUTCOME_FAILED = "failed"
OUTCOME_SERVER_ERROR = "server_error"


class GradingDisposition(StrEnum):
    """Why LLM grading was requested or skipped for a verification run."""

    REQUESTED = "requested"
    NOT_REQUIRED = "not_required"
    SKIPPED_GATE_FAILED = "skipped_gate_failed"
    SKIPPED_MISSING_USERNAME = "skipped_missing_username"
    SKIPPED_UNKNOWN_SUBMISSION_TYPE = "skipped_unknown_submission_type"


@dataclass(frozen=True, slots=True)
class PreparedVerificationAttempt:
    """Serializable verification attempt input for workflow activities."""

    id: UUID
    user_id: int
    github_username: str | None
    requirement: HandsOnRequirement
    submitted_value: SubmittedValue

    def to_payload(self) -> dict[str, object]:
        return {
            "id": str(self.id),
            "user_id": self.user_id,
            "github_username": self.github_username,
            "requirement": self.requirement.model_dump(mode="json"),
            "submission_value": self.submitted_value.to_payload(),
        }

    @property
    def target(self) -> GitHubTarget | None:
        return build_target(self.requirement, self.github_username)

    @classmethod
    def from_payload(cls, payload: Mapping[str, object]) -> PreparedVerificationAttempt:
        github_username = payload.get("github_username")
        requirement = HandsOnRequirementAdapter.validate_python(payload["requirement"])
        return cls(
            id=UUID(_expect_str(payload["id"], "id")),
            user_id=_expect_int(payload["user_id"], "user_id"),
            github_username=(
                _expect_str(github_username, "github_username")
                if github_username is not None
                else None
            ),
            requirement=requirement,
            submitted_value=SubmittedValue.from_payload(payload["submission_value"]),
        )


@dataclass(frozen=True, slots=True)
class VerificationRunResult:
    """Serializable result carried between verification activities."""

    attempt: PreparedVerificationAttempt
    validation_result: ValidationResult
    evidence: list[EvidenceBundle] | None = None
    grading_requests: list[LLMGradingRequest] | None = None
    grading_disposition: GradingDisposition | None = None

    def to_payload(self) -> dict[str, object]:
        return {
            "attempt": self.attempt.to_payload(),
            "validation_result": self.validation_result.model_dump(mode="json"),
            "evidence": (
                [bundle.model_dump(mode="json") for bundle in self.evidence]
                if self.evidence is not None
                else None
            ),
            "grading_requests": (
                [request.model_dump(mode="json") for request in self.grading_requests]
                if self.grading_requests is not None
                else None
            ),
            "grading_disposition": (
                self.grading_disposition.value
                if self.grading_disposition is not None
                else None
            ),
        }

    @classmethod
    def from_payload(cls, payload: Mapping[str, object]) -> VerificationRunResult:
        raw_evidence = payload.get("evidence")
        evidence = (
            [EvidenceBundle.model_validate(bundle) for bundle in raw_evidence]
            if isinstance(raw_evidence, list)
            else None
        )
        raw_requests = payload.get("grading_requests")
        grading_requests = (
            [LLMGradingRequest.model_validate(request) for request in raw_requests]
            if isinstance(raw_requests, list)
            else None
        )
        raw_disposition = payload.get("grading_disposition")
        grading_disposition = (
            GradingDisposition(_expect_str(raw_disposition, "grading_disposition"))
            if raw_disposition is not None
            else None
        )
        return cls(
            attempt=PreparedVerificationAttempt.from_payload(
                _expect_mapping(payload["attempt"])
            ),
            validation_result=ValidationResult.model_validate(
                payload["validation_result"]
            ),
            evidence=evidence,
            grading_requests=grading_requests,
            grading_disposition=grading_disposition,
        )

    def without_transport_data(self) -> VerificationRunResult:
        """Drop evidence and grading prompts before the database write."""
        if self.evidence is None and self.grading_requests is None:
            return self
        return replace(self, evidence=None, grading_requests=None)


def outcome_for_validation(validation_result: ValidationResult) -> str:
    if validation_result.is_valid:
        return OUTCOME_SUCCEEDED
    if validation_result.verification_completed:
        return OUTCOME_FAILED
    return OUTCOME_SERVER_ERROR


def code_for_outcome(outcome: str, fallback: str | None = None) -> str:
    if outcome == OUTCOME_SUCCEEDED:
        return VERIFICATION_SUCCEEDED_CODE
    if outcome == OUTCOME_FAILED:
        return fallback or VALIDATION_FAILED_ERROR_CODE
    return fallback or VERIFICATION_INCOMPLETE_ERROR_CODE


def _expect_mapping(value: object) -> Mapping[str, object]:
    if not isinstance(value, Mapping):
        raise TypeError("Expected payload object")
    payload: dict[str, object] = {}
    for key, item in value.items():
        if not isinstance(key, str):
            raise TypeError("Expected string payload keys")
        payload[key] = item
    return payload


def _expect_int(value: object, field_name: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool):
        raise TypeError(f"Expected integer payload field: {field_name}")
    return value


def _expect_str(value: object, field_name: str) -> str:
    if not isinstance(value, str):
        raise TypeError(f"Expected string payload field: {field_name}")
    return value
