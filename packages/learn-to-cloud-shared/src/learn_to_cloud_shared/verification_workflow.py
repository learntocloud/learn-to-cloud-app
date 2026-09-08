"""Typed inputs and results for verification execution."""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from learn_to_cloud_shared.github_repository_target import GitHubRepositoryTarget
from learn_to_cloud_shared.schemas import (
    HandsOnRequirement,
    ValidationResult,
)
from learn_to_cloud_shared.submission_derivation import build_target
from learn_to_cloud_shared.submission_values import SubmittedValue
from learn_to_cloud_shared.verification.grading_requests import LLMGradingRequest

VALIDATION_FAILED_ERROR_CODE = "validation_failed"
VERIFICATION_INCOMPLETE_ERROR_CODE = "verification_incomplete"
VERIFICATION_SUCCEEDED_CODE = "verification_succeeded"

OUTCOME_SUCCEEDED = "succeeded"
OUTCOME_FAILED = "failed"
OUTCOME_SERVER_ERROR = "server_error"
LLM_ERROR_TYPES = frozenset(
    {
        "llm.configuration",
        "llm.authentication",
        "llm.authorization",
        "llm.rate_limit",
        "llm.provider_unavailable",
        "llm.network",
        "llm.timeout",
        "llm.response_validation",
        "llm.unknown",
    }
)


@dataclass(frozen=True, slots=True)
class PreparedVerificationAttempt:
    """Validated attempt input loaded from its stored snapshot."""

    id: UUID
    user_id: int
    github_username: str | None
    requirement: HandsOnRequirement
    submitted_value: SubmittedValue

    @property
    def target(self) -> GitHubRepositoryTarget | None:
        return build_target(self.requirement, self.github_username)


@dataclass(frozen=True, slots=True)
class VerificationRunResult:
    """Verification output with optional evidence awaiting rubric grading."""

    attempt: PreparedVerificationAttempt
    validation_result: ValidationResult
    grading_requests: list[LLMGradingRequest] | None = None
    llm_error_type: str | None = None


def outcome_for_validation(validation_result: ValidationResult) -> str:
    if not validation_result.verification_completed:
        return OUTCOME_SERVER_ERROR
    if validation_result.is_valid:
        return OUTCOME_SUCCEEDED
    return OUTCOME_FAILED


def code_for_outcome(outcome: str, fallback: str | None = None) -> str:
    if outcome == OUTCOME_SUCCEEDED:
        return VERIFICATION_SUCCEEDED_CODE
    if outcome == OUTCOME_FAILED:
        return fallback or VALIDATION_FAILED_ERROR_CODE
    return fallback or VERIFICATION_INCOMPLETE_ERROR_CODE
