"""Shared verification result helpers."""

from __future__ import annotations

from learn_to_cloud_shared.models import (
    VerificationAttemptOutcome,
)
from learn_to_cloud_shared.repositories.verification_attempt_repository import (
    AttemptCardProjection,
)
from learn_to_cloud_shared.schemas import (
    SubmissionData,
)

MAX_VALIDATION_MESSAGE_LENGTH = 1024


def persisted_validation_message(message: str | None) -> str | None:
    """Return a validation message that fits persisted status columns."""
    if message is None or len(message) <= MAX_VALIDATION_MESSAGE_LENGTH:
        return message
    return f"{message[: MAX_VALIDATION_MESSAGE_LENGTH - 3]}..."


def attempt_to_submission_data(attempt: AttemptCardProjection) -> SubmissionData:
    """Project a terminal verification attempt into its response model."""
    outcome = VerificationAttemptOutcome(attempt.outcome)
    is_validated = outcome is VerificationAttemptOutcome.SUCCEEDED
    verification_completed = outcome in (
        VerificationAttemptOutcome.SUCCEEDED,
        VerificationAttemptOutcome.FAILED,
    )
    return SubmissionData(
        submitted_value=attempt.submitted_value,
        is_validated=is_validated,
        validated_at=attempt.completed_at if is_validated else None,
        verification_completed=verification_completed,
        validation_message=(attempt.validation_message if not is_validated else None),
        error_code=attempt.error_code,
    )
