"""Queue verification attempts and read their persisted polling state."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from enum import StrEnum
from uuid import UUID

from learn_to_cloud_shared.repositories.verification_attempt_repository import (
    VerificationAttemptRepository,
)
from learn_to_cloud_shared.submission_values import SubmittedValue
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from learn_to_cloud.services.submissions_service import create_verification_attempt

logger = logging.getLogger(__name__)

INITIAL_VERIFICATION_STATUS_DELAY_SECONDS = 2
RUNNING_VERIFICATION_STATUS_DELAY_SECONDS = 5


class VerificationPollKind(StrEnum):
    PROCESSING = "processing"
    RELOAD = "reload"
    UNEXPECTED = "unexpected"


@dataclass(frozen=True, slots=True)
class VerificationPollResult:
    """Polling decision for an owned attempt."""

    kind: VerificationPollKind
    requirement_uuid: UUID


async def submit_verification_attempt(
    *,
    session_maker: async_sessionmaker[AsyncSession],
    user_id: int,
    github_username: str,
    requirement_slug: str,
    submitted_value: SubmittedValue,
) -> UUID:
    """Commit an attempt for the worker and return its polling ID."""
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
            "verification.requirement.slug": requirement_slug,
            "verification.attempt.id": str(attempt_submission.attempt_id),
            "verification.attempt.created": attempt_submission.created,
        },
    )
    return attempt_submission.attempt_id


async def poll_verification_attempt(
    *,
    session_maker: async_sessionmaker[AsyncSession],
    user_id: int,
    attempt_id: UUID,
) -> VerificationPollResult | None:
    """Read status only after verifying ownership; never finalize an attempt."""
    async with session_maker() as session:
        attempt = await VerificationAttemptRepository(session).get_status(attempt_id)

    if attempt is None or attempt.user_id != user_id:
        return None
    if attempt.outcome is None:
        kind = VerificationPollKind.PROCESSING
    elif attempt.outcome in {"succeeded", "failed", "server_error", "cancelled"}:
        kind = VerificationPollKind.RELOAD
    else:
        kind = VerificationPollKind.UNEXPECTED
    return VerificationPollResult(kind, attempt.requirement_uuid)
