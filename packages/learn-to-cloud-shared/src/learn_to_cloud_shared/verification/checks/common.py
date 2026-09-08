"""Shared result contracts for check adapters."""

from learn_to_cloud_shared.schemas import ValidationResult
from learn_to_cloud_shared.verification.core import StepResult


def validation_step_result(result: ValidationResult) -> StepResult:
    """Wrap the authoritative result without copying it."""
    return StepResult(
        passed=result.is_valid,
        stop_on_fail=True,
        validation_result=result,
    )


def missing_repository_result() -> StepResult:
    """Report incomplete configuration for checks requiring a repository."""
    return validation_step_result(
        ValidationResult(
            is_valid=False,
            message="Requirement configuration error: missing required_repo",
            verification_completed=False,
            error_code="evidence.configuration",
            username_match=True,
            repo_exists=False,
        )
    )
