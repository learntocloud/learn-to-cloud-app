"""Verification submission and result models."""

from datetime import datetime
from typing import Literal

from pydantic import Field

from learn_to_cloud.schemas.base import FrozenModel


class SubmissionData(FrozenModel):
    """Learner-facing state from the latest terminal verification attempt."""

    submitted_value: str
    is_validated: bool
    validated_at: datetime | None = None
    verification_completed: bool = False
    validation_message: str | None = None
    error_code: str | None = None


class TaskResult(FrozenModel):
    """Result of verifying a single task in a multi-task verification.

    Used by DEVOPS_VERIFICATION and SECURITY_SCANNING validations to provide
    detailed per-task feedback.
    """

    task_name: str
    passed: bool
    feedback: str
    next_steps: str = ""
    criterion_results: list["CriterionResult"] = Field(default_factory=list)


class CriterionResult(FrozenModel):
    """Learner-facing result for one rubric criterion."""

    criterion_id: str
    label: str = ""
    kind: Literal["required", "quality", "bonus"] = "required"
    status: Literal["met", "not_met", "not_applicable"]
    explanation: str
    next_steps: str = ""
    evidence_refs: list[str] = Field(default_factory=list)


class PhaseSubmissionContext(FrozenModel):
    """Pre-built submission context for rendering a phase page."""

    submissions_by_req: dict[str, SubmissionData]
    feedback_by_req: dict[str, dict[str, object]]


class ValidationResult(FrozenModel):
    """Result of validating a hands-on submission.

    This is the common result type for ALL validation types.

    Attributes:
        is_valid: Whether the submission passed validation.
        message: User-facing message explaining the result.
        username_match: For GitHub-based validations, whether the submitted
            URL matches the authenticated user. None for non-GitHub validations.
        repo_exists: For GitHub-based validations, whether the repository
            exists. None for non-GitHub validations.
        task_results: For multi-task validations, detailed per-task feedback.
            None for single-check validations.
        verification_completed: False if validation failed due to a server-side
            issue (e.g., service unavailable, config error). When False, the
            attempt is not counted since the user isn't at fault.
        cloud_provider: Cloud provider for multi-cloud labs ("aws",
            "azure", "gcp"). None for non-multi-cloud validations.
    """

    is_valid: bool
    message: str
    username_match: bool | None = None
    repo_exists: bool | None = None
    task_results: list[TaskResult] | None = None
    verification_completed: bool = True
    cloud_provider: str | None = None
    error_code: str | None = None
