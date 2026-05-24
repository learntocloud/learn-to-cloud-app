"""Shared verification execution and submission persistence helpers."""

from __future__ import annotations

import json
import logging
from collections.abc import Awaitable, Callable

from opentelemetry import trace
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

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
from learn_to_cloud_shared.verification.dispatcher import validate_submission
from learn_to_cloud_shared.verification.github_profile import parse_github_url

logger = logging.getLogger(__name__)
tracer = trace.get_tracer(__name__)

SubmissionPersistHook = Callable[
    [AsyncSession, Submission, ValidationResult],
    Awaitable[None],
]
MAX_VALIDATION_MESSAGE_LENGTH = 1024


class SubmissionAlreadyInFlightError(Exception):
    """Raised when a sync verification is already running for the same requirement.

    Used as a dedupe signal when two concurrent submits (e.g. a double-click)
    arrive for the same ``(user_id, requirement_id)``. The first one holds a
    Postgres transactional advisory lock; the second one sees the lock is
    busy and bails out so the user can wait for the first to finish.
    """


def persisted_validation_message(message: str | None) -> str | None:
    """Return a validation message that fits persisted status columns."""
    if message is None or len(message) <= MAX_VALIDATION_MESSAGE_LENGTH:
        return message
    return f"{message[: MAX_VALIDATION_MESSAGE_LENGTH - 3]}..."


def to_submission_data(submission: Submission) -> SubmissionData:
    """Project a ``Submission`` row into the ``SubmissionData`` response model.

    Phase D.2 + D.3 (#461 / #465) removed the denormalized
    ``requirement_id`` / ``submission_type`` / ``phase_id`` fields from
    both the table and the schema -- callers that need them work off
    the in-memory ``HandsOnRequirement`` directly.
    """
    return SubmissionData(
        id=submission.id,
        submitted_value=submission.submitted_value,
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
    submitted_value: str,
    github_username: str | None,
) -> str | None:
    if requirement.submission_type in (
        SubmissionType.CTF_TOKEN,
        SubmissionType.NETWORKING_TOKEN,
    ):
        return github_username

    parsed = parse_github_url(submitted_value)
    return parsed.username if parsed.is_valid else None


def _feedback_json(validation_result: ValidationResult) -> str | None:
    if not validation_result.task_results:
        return None
    return json.dumps([task.model_dump() for task in validation_result.task_results])


async def persist_validation_result(
    db: AsyncSession,
    *,
    user_id: int,
    requirement: HandsOnRequirement,
    submitted_value: str,
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
            submitted_value,
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


async def execute_submission_validation(
    *,
    session_maker: async_sessionmaker[AsyncSession],
    user_id: int,
    requirement: HandsOnRequirement,
    submitted_value: str,
    github_username: str | None,
    after_persist: SubmissionPersistHook | None = None,
) -> SubmissionResult:
    """Run validation without holding a DB session, then persist the result."""
    with tracer.start_as_current_span(
        "execute_submission_validation",
        attributes={
            "user.id": user_id,
            "requirement.id": requirement.id,
            "submission.type": requirement.submission_type.value,
        },
    ) as span:
        validation_result = await validate_submission(
            requirement=requirement,
            submitted_value=submitted_value,
            expected_username=github_username,
        )

        async with session_maker() as write_session:
            db_submission = await persist_validation_result(
                write_session,
                user_id=user_id,
                requirement=requirement,
                submitted_value=submitted_value,
                github_username=github_username,
                validation_result=validation_result,
            )
            if after_persist is not None:
                await after_persist(write_session, db_submission, validation_result)
            await write_session.commit()

        span.set_attribute("submission.is_valid", validation_result.is_valid)
        span.set_attribute(
            "submission.verification_completed",
            validation_result.verification_completed,
        )

        logger.info(
            "submission.completed",
            extra={
                "user_id": user_id,
                "requirement_id": requirement.id,
                "submission_type": requirement.submission_type,
                "is_valid": validation_result.is_valid,
                "verification_completed": validation_result.verification_completed,
                "validation_message": (
                    validation_result.message
                    if not validation_result.is_valid
                    else None
                ),
            },
        )

        return build_submission_result(db_submission, validation_result)


def _advisory_lock_key(user_id: int, requirement_id: str) -> str:
    """Stable Postgres advisory-lock key for one (user, requirement) pair.

    Namespaced so it can't collide with any other advisory locks the app
    may take in the future.
    """
    return f"verification-sub:{user_id}:{requirement_id}"


async def execute_sync_submission_validation(
    *,
    session_maker: async_sessionmaker[AsyncSession],
    user_id: int,
    requirement: HandsOnRequirement,
    submitted_value: str,
    github_username: str | None,
) -> SubmissionResult:
    """Run a sync (sub-second) verification in one DB transaction.

    Used for submission types that finish quickly enough to answer from
    the same HTTP request — no Durable Functions, no spinner, no polling.

    Concurrency: takes a Postgres transactional advisory lock keyed on
    ``(user_id, requirement_id)`` so two parallel submits (e.g. a
    double-click) can't both run validation and race
    ``Submission.attempt_number`` into a duplicate-key crash. If the lock
    is already held, raises :class:`SubmissionAlreadyInFlightError`.

    The DB connection is held across the validator call (typically a
    single GitHub API request, ~200-500ms). Lock contention is bounded to
    the same user submitting the same requirement, so pool pressure
    stays negligible.
    """
    lock_key = _advisory_lock_key(user_id, requirement.id)

    with tracer.start_as_current_span(
        "execute_sync_submission_validation",
        attributes={
            "user.id": user_id,
            "requirement.id": requirement.id,
            "submission.type": requirement.submission_type.value,
        },
    ) as span:
        async with session_maker() as session, session.begin():
            acquired = await session.scalar(
                text("SELECT pg_try_advisory_xact_lock(hashtext(:key))"),
                {"key": lock_key},
            )
            if not acquired:
                span.set_attribute("submission.lock_acquired", False)
                raise SubmissionAlreadyInFlightError(
                    "A verification for this requirement is already in progress. "
                    "Please wait a moment and try again."
                )
            span.set_attribute("submission.lock_acquired", True)

            validation_result = await validate_submission(
                requirement=requirement,
                submitted_value=submitted_value,
                expected_username=github_username,
            )

            db_submission = await persist_validation_result(
                session,
                user_id=user_id,
                requirement=requirement,
                submitted_value=submitted_value,
                github_username=github_username,
                validation_result=validation_result,
            )

        span.set_attribute("submission.is_valid", validation_result.is_valid)
        span.set_attribute(
            "submission.verification_completed",
            validation_result.verification_completed,
        )

        logger.info(
            "submission.completed",
            extra={
                "user_id": user_id,
                "requirement_id": requirement.id,
                "submission_type": requirement.submission_type,
                "is_valid": validation_result.is_valid,
                "verification_completed": validation_result.verification_completed,
                "validation_message": (
                    validation_result.message
                    if not validation_result.is_valid
                    else None
                ),
                "execution_path": "sync",
            },
        )

        return build_submission_result(db_submission, validation_result)
