"""Shared verification execution and submission persistence helpers."""

from __future__ import annotations

import logging

from opentelemetry import trace
from sqlalchemy.ext.asyncio import AsyncSession

from learn_to_cloud_shared.github_target import GitHubTarget
from learn_to_cloud_shared.models import Submission, SubmissionType
from learn_to_cloud_shared.repositories.submission_repository import (
    SubmissionRepository,
)
from learn_to_cloud_shared.schemas import (
    HandsOnRequirement,
    SubmissionData,
    SubmissionResult,
    ValidationResult,
)
from learn_to_cloud_shared.submission_values import (
    SubmittedValue,
    submission_value_from_columns,
)

logger = logging.getLogger(__name__)
tracer = trace.get_tracer(__name__)

MAX_VALIDATION_MESSAGE_LENGTH = 1024


def persisted_validation_message(message: str | None) -> str | None:
    """Return a validation message that fits persisted status columns."""
    if message is None or len(message) <= MAX_VALIDATION_MESSAGE_LENGTH:
        return message
    return f"{message[: MAX_VALIDATION_MESSAGE_LENGTH - 3]}..."


def _log_submission_completed(
    *,
    user_id: int,
    requirement: HandsOnRequirement,
    validation_result: ValidationResult,
    execution_path: str | None = None,
) -> None:
    """Log the canonical one-line submission outcome.

    Normal outcomes, including learner-fault failures, log at INFO. When the
    check could not complete because of an our-side or upstream fault
    (``verification_completed=False``), log at WARNING so operators can find
    and alert on it by severity instead of digging through traces.
    """
    extra: dict[str, object] = {
        "user_id": user_id,
        "requirement_slug": requirement.slug,
        "submission_type": requirement.submission_type,
        "is_valid": validation_result.is_valid,
        "verification_completed": validation_result.verification_completed,
        "validation_message": (
            validation_result.message if not validation_result.is_valid else None
        ),
    }
    if execution_path is not None:
        extra["execution_path"] = execution_path
    level = (
        logging.INFO if validation_result.verification_completed else logging.WARNING
    )
    logger.log(level, "submission.completed", extra=extra)


def to_submission_data(submission: Submission) -> SubmissionData:
    """Project a ``Submission`` row into the ``SubmissionData`` response model.

    Phase D.2 + D.3 (#461 / #465) removed the denormalized
    ``requirement_slug`` / ``submission_type`` / ``phase_id`` fields from
    both the table and the schema -- callers that need them work off
    the in-memory ``HandsOnRequirement`` directly.
    """
    return SubmissionData(
        id=submission.id,
        submitted_value=submission_value_from_columns(submission).as_text,
        extracted_username=submission.extracted_username,
        is_validated=submission.is_validated,
        validated_at=submission.validated_at,
        verification_completed=submission.verification_completed,
        feedback_json=submission.feedback_json,
        validation_message=submission.validation_message,
        cloud_provider=submission.cloud_provider,
        created_at=submission.created_at,
        updated_at=submission.updated_at,
    )


def _extract_username(
    requirement: HandsOnRequirement,
    target: GitHubTarget | None,
    github_username: str | None,
) -> str | None:
    """Return the GitHub username tied to this submission, if any.

    Tokens carry no GitHub location but are still tied to the authenticated
    learner. Repo/profile types own a constructed target whose owner is that
    same learner. Free-form types (deployed API, career reflection) have
    neither, so they record no username.
    """
    if requirement.submission_type in (
        SubmissionType.CTF_TOKEN,
        SubmissionType.NETWORKING_TOKEN,
    ):
        return github_username
    return target.owner if target is not None else None


def _feedback_json(validation_result: ValidationResult) -> list[dict] | None:
    if not validation_result.task_results:
        return None
    return [task.model_dump() for task in validation_result.task_results]


async def persist_validation_result(
    db: AsyncSession,
    *,
    user_id: int,
    requirement: HandsOnRequirement,
    submitted_value: SubmittedValue,
    target: GitHubTarget | None,
    github_username: str | None,
    validation_result: ValidationResult,
) -> Submission:
    """Persist one validation attempt as a Submission row."""
    submission_repo = SubmissionRepository(db)
    return await submission_repo.create(
        user_id=user_id,
        requirement_uuid=requirement.uuid,
        submitted_value=submitted_value,
        extracted_username=_extract_username(
            requirement,
            target,
            github_username,
        ),
        is_validated=validation_result.is_valid,
        verification_completed=validation_result.verification_completed,
        feedback_json=_feedback_json(validation_result),
        validation_message=(
            persisted_validation_message(validation_result.message)
            if not validation_result.is_valid
            else None
        ),
        cloud_provider=validation_result.cloud_provider,
    )


def build_submission_result(
    submission: Submission,
    validation_result: ValidationResult,
) -> SubmissionResult:
    return SubmissionResult(
        submission=to_submission_data(submission),
        is_valid=validation_result.is_valid,
        message=validation_result.message,
        username_match=validation_result.username_match,
        repo_exists=validation_result.repo_exists,
        task_results=validation_result.task_results,
    )
