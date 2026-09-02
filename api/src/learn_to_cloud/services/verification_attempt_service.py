"""Coordinate verification attempt startup and Durable status polling."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from enum import StrEnum
from uuid import UUID

from learn_to_cloud_shared.repositories.verification_attempt_repository import (
    VerificationAttemptRepository,
)
from learn_to_cloud_shared.submission_values import SubmittedValue
from learn_to_cloud_shared.verification_attempt_executor import (
    terminalize_unstarted_verification_attempt,
    terminalize_verification_attempt,
)
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from learn_to_cloud.services.durable_verification_client import (
    DurableVerificationAuthError,
    DurableVerificationConfigError,
    DurableVerificationStartError,
    get_verification_attempt_status,
    start_verification_attempt_orchestration,
)
from learn_to_cloud.services.submissions_service import (
    VerificationAttemptSubmission,
    create_verification_attempt,
)
from learn_to_cloud.services.verification_status_tokens import (
    VerificationStatusToken,
    create_verification_status_token,
)

logger = logging.getLogger(__name__)

INITIAL_VERIFICATION_STATUS_DELAY_SECONDS = 2
RUNNING_VERIFICATION_STATUS_DELAY_SECONDS = 5

_DURABLE_START_ERROR_MESSAGE = (
    "Verification could not be started because of a problem with the verification "
    "service. This attempt was not counted. Please try again later or report the "
    "issue if it keeps failing."
)
_ACTIVE_DURABLE_STATUSES = {"pending", "running", "continuedasnew"}
_TERMINAL_DURABLE_STATUSES = {"completed", "failed", "terminated", "canceled"}
_DURABLE_FAILURE_STATUSES = {"failed", "terminated", "canceled"}


@dataclass(frozen=True, slots=True)
class VerificationStartResult:
    """Result needed by the HTTP layer after starting an attempt."""

    status_token: str | None
    unavailable_message: str | None = None


class VerificationPollKind(StrEnum):
    PROCESSING = "processing"
    RELOAD = "reload"
    UNEXPECTED = "unexpected"


@dataclass(frozen=True, slots=True)
class VerificationPollResult:
    """Durable polling decision for the HTTP layer."""

    kind: VerificationPollKind
    token_data: VerificationStatusToken
    runtime_status: str


async def submit_verification_attempt(
    *,
    session_maker: async_sessionmaker[AsyncSession],
    user_id: int,
    github_username: str,
    requirement_slug: str,
    submitted_value: SubmittedValue,
) -> VerificationStartResult:
    """Create an attempt, start Durable, and return the polling token."""
    attempt_submission = await create_verification_attempt(
        session_maker=session_maker,
        user_id=user_id,
        requirement_slug=requirement_slug,
        submitted_value=submitted_value,
        github_username=github_username,
    )
    logger.info(
        "verification.attempt.created",
        extra={
            "user_id": user_id,
            "requirement_slug": requirement_slug,
            "attempt_id": str(attempt_submission.attempt_id),
            "attempt_created": attempt_submission.created,
        },
    )
    return await _start_verification_attempt(
        session_maker=session_maker,
        user_id=user_id,
        requirement_slug=requirement_slug,
        attempt_submission=attempt_submission,
    )


async def _start_verification_attempt(
    *,
    session_maker: async_sessionmaker[AsyncSession],
    user_id: int,
    requirement_slug: str,
    attempt_submission: VerificationAttemptSubmission,
) -> VerificationStartResult:
    try:
        if attempt_submission.created:
            await start_verification_attempt_orchestration(
                attempt_submission.attempt_id
            )

        return VerificationStartResult(
            status_token=create_verification_status_token(
                user_id=user_id,
                job_id=attempt_submission.attempt_id,
                instance_id=str(attempt_submission.attempt_id),
                requirement_slug=requirement_slug,
            )
        )
    except (
        DurableVerificationConfigError,
        DurableVerificationAuthError,
        DurableVerificationStartError,
    ) as exc:
        logger.exception(
            "verification.attempt.durable_start_failed",
            extra={
                "requirement_slug": requirement_slug,
                "attempt_id": str(attempt_submission.attempt_id),
                "error_type": type(exc).__name__,
                "failure_kind": exc.failure_kind.value,
                "status_code": exc.status_code,
            },
        )
        await terminalize_unstarted_verification_attempt(
            attempt_submission.attempt_id,
            error_code=exc.error_code,
            validation_message="Verification could not be started.",
            terminal_source="api_start_failure",
            session_maker=session_maker,
        )
        return VerificationStartResult(
            status_token=None,
            unavailable_message=_DURABLE_START_ERROR_MESSAGE,
        )


async def poll_verification_attempt(
    *,
    session_maker: async_sessionmaker[AsyncSession],
    user_id: int,
    token_data: VerificationStatusToken,
) -> VerificationPollResult:
    """Read Durable state and persist any terminal failure."""
    durable_status = await get_verification_attempt_status(token_data.instance_id)
    status = durable_status.runtime_status.lower()

    if status in _ACTIVE_DURABLE_STATUSES:
        return VerificationPollResult(
            VerificationPollKind.PROCESSING,
            token_data,
            status,
        )

    if status in _DURABLE_FAILURE_STATUSES:
        await _terminalize_failed_attempt(
            session_maker,
            token_data,
            status,
        )
        return VerificationPollResult(
            VerificationPollKind.RELOAD,
            token_data,
            status,
        )

    if status in _TERMINAL_DURABLE_STATUSES:
        await _log_attempt_completion(session_maker, token_data, user_id, status)
        return VerificationPollResult(
            VerificationPollKind.RELOAD,
            token_data,
            status,
        )

    logger.warning(
        "verification.status.unexpected_durable_status",
        extra={
            "attempt_id": token_data.job_id,
            "runtime_status": durable_status.runtime_status,
        },
    )
    return VerificationPollResult(
        VerificationPollKind.UNEXPECTED,
        token_data,
        status,
    )


async def _terminalize_failed_attempt(
    session_maker: async_sessionmaker[AsyncSession],
    token_data: VerificationStatusToken,
    status: str,
) -> None:
    attempt_id = UUID(token_data.job_id)
    async with session_maker() as session:
        if await VerificationAttemptRepository(session).get_status(attempt_id) is None:
            return

    cancelled = status in {"terminated", "canceled"}
    result = await terminalize_verification_attempt(
        attempt_id,
        outcome="cancelled" if cancelled else "server_error",
        error_code="cancelled" if cancelled else "server_error",
        validation_message=(
            "Verification was cancelled."
            if cancelled
            else "Verification failed before recording a result."
        ),
        terminal_source="poller",
        session_maker=session_maker,
    )
    if not result.won:
        logger.info(
            "verification.poller.finalize_skipped",
            extra={
                "attempt_id": str(attempt_id),
                "runtime_status": status,
                "outcome": result.state.outcome,
            },
        )
        return

    logger.info(
        "verification.poller.attempt_terminalized",
        extra={
            "attempt_id": str(attempt_id),
            "runtime_status": status,
            "outcome": result.state.outcome,
            "cas_won": result.won,
        },
    )


async def _log_attempt_completion(
    session_maker: async_sessionmaker[AsyncSession],
    token_data: VerificationStatusToken,
    user_id: int,
    status: str,
) -> None:
    attempt_id = UUID(token_data.job_id)
    try:
        async with session_maker() as session:
            state = await VerificationAttemptRepository(session).get_terminal_state(
                attempt_id
            )
    except SQLAlchemyError as exc:
        logger.warning(
            "verification.attempt.completed_read_failed",
            extra={
                "user_id": user_id,
                "requirement_slug": token_data.requirement_slug,
                "attempt_id": str(attempt_id),
                "error_type": type(exc).__name__,
            },
        )
        return

    extra = {
        "user_id": user_id,
        "requirement_slug": token_data.requirement_slug,
        "attempt_id": str(attempt_id),
        "runtime_status": status,
        "outcome": state.outcome if state else None,
        "error_code": state.error_code if state else None,
        "terminal_source": state.terminal_source if state else None,
    }
    if state is None or state.outcome == "server_error":
        logger.warning("verification.attempt.observed", extra=extra)
    else:
        logger.info("verification.attempt.observed", extra=extra)
