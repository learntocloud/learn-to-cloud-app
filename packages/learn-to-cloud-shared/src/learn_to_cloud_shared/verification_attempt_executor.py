"""Load trusted attempt snapshots and commit outcomes without overwriting results."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from learn_to_cloud_shared.core.logger import APP_LOGGER_NAMESPACE
from learn_to_cloud_shared.models import VerificationAttemptOutcome
from learn_to_cloud_shared.repositories.verification_attempt_repository import (
    FinalizeResult,
    VerificationAttemptRepository,
)
from learn_to_cloud_shared.submission_values import (
    submitted_value_from_kind_and_value,
    value_kind_for_submission_type,
)
from learn_to_cloud_shared.verification.evidence import EVIDENCE_ERROR_CODES
from learn_to_cloud_shared.verification.execution import (
    persisted_validation_message,
)
from learn_to_cloud_shared.verification_attempt_snapshot import (
    SUPPORTED_PAYLOAD_VERSIONS,
    AttemptSnapshotError,
    validate_snapshot_integrity,
)
from learn_to_cloud_shared.verification_workflow import (
    LLM_ERROR_TYPES,
    PreparedVerificationAttempt,
    VerificationRunResult,
    code_for_outcome,
    outcome_for_validation,
)

logger = logging.getLogger(f"{APP_LOGGER_NAMESPACE}.verification_attempt_executor")

_SNAPSHOT_SOURCE_SUBMITTED = "submitted"
_WORKER_TERMINAL_SOURCE = "api_worker"
_VALIDATION_ERROR_CODES = EVIDENCE_ERROR_CODES | {
    "authentication",
    "authorization",
    "client_error",
    "network",
    "provider_unavailable",
    "rate_limit",
}


class AttemptPreparationError(Exception):
    """Base for attempt preparation failures (all lead to terminalization)."""


class AttemptNotFoundError(AttemptPreparationError):
    """The attempt id does not exist."""


class AttemptNotActiveError(AttemptPreparationError):
    """The attempt already reached a terminal outcome."""


class AttemptNotRunnableError(AttemptPreparationError):
    """The attempt cannot be executed (e.g. a reconstructed backfill row)."""


@dataclass(frozen=True, slots=True)
class AttemptPreparation:
    """A validated attempt ready for execution."""

    attempt: PreparedVerificationAttempt


async def prepare_verification_attempt(
    attempt_id: UUID,
    *,
    session_maker: async_sessionmaker[AsyncSession],
) -> AttemptPreparation:
    """Load and validate the stored snapshot before verification."""
    async with session_maker() as db:
        repo = VerificationAttemptRepository(db)
        state = await repo.get_prepare_state(attempt_id)
        if state is None:
            raise AttemptNotFoundError(str(attempt_id))
        if state.outcome is not None:
            raise AttemptNotActiveError(
                f"attempt {attempt_id} is already terminal ({state.outcome})"
            )
        if state.started_at is None:
            marked_started = await repo.mark_started(attempt_id)
            if not marked_started:
                current = await repo.get_status(attempt_id)
                if current is None:
                    raise AttemptNotFoundError(str(attempt_id))
                if current.outcome is not None:
                    raise AttemptNotActiveError(
                        f"attempt {attempt_id} is already terminal ({current.outcome})"
                    )
            await db.commit()
    if state.snapshot_source != _SNAPSHOT_SOURCE_SUBMITTED:
        raise AttemptNotRunnableError(
            f"attempt {attempt_id} has non-runnable snapshot_source "
            f"{state.snapshot_source!r}"
        )
    if state.payload_version not in SUPPORTED_PAYLOAD_VERSIONS:
        raise AttemptSnapshotError(
            f"attempt {attempt_id} payload_version "
            f"{state.payload_version!r} is not supported"
        )

    requirement = validate_snapshot_integrity(
        snapshot=state.requirement_snapshot,
        snapshot_hash=state.requirement_snapshot_hash,
    )

    expected_kind = value_kind_for_submission_type(requirement.submission_type)
    if state.submission_value_kind != expected_kind.value:
        raise AttemptSnapshotError(
            f"attempt {attempt_id} submission_value_kind "
            f"{state.submission_value_kind!r} does not match requirement "
            f"kind {expected_kind.value!r}"
        )

    submitted_value = submitted_value_from_kind_and_value(
        state.submission_value_kind,
        state.submitted_value,
    )
    attempt = PreparedVerificationAttempt(
        id=state.id,
        user_id=state.user_id,
        github_username=state.github_username_snapshot,
        requirement=requirement,
        submitted_value=submitted_value,
    )
    return AttemptPreparation(attempt=attempt)


async def finalize_verification_attempt(
    run_result: VerificationRunResult,
    *,
    session_maker: async_sessionmaker[AsyncSession],
) -> FinalizeResult:
    """Persist an attempt's real verification outcome via compare-and-set."""
    run_result = run_result.without_transport_data()
    attempt = run_result.attempt
    validation_result = run_result.validation_result
    outcome = outcome_for_validation(validation_result)
    error_code = (
        run_result.llm_error_type
        if run_result.llm_error_type in LLM_ERROR_TYPES
        else code_for_outcome(
            outcome,
            validation_result.error_code
            if validation_result.error_code in _VALIDATION_ERROR_CODES
            else None,
        )
    )
    validation_message = (
        persisted_validation_message(validation_result.message)
        if not validation_result.is_valid
        else None
    )
    feedback_json = (
        [task.model_dump() for task in validation_result.task_results]
        if validation_result.task_results
        else None
    )

    return await _finalize(
        attempt.id,
        session_maker=session_maker,
        outcome=VerificationAttemptOutcome(outcome),
        error_code=error_code,
        validation_message=validation_message,
        terminal_source=_WORKER_TERMINAL_SOURCE,
        feedback_json=feedback_json,
    )


async def terminalize_verification_attempt(
    attempt_id: UUID,
    *,
    outcome: VerificationAttemptOutcome | str,
    error_code: str,
    validation_message: str,
    terminal_source: str,
    session_maker: async_sessionmaker[AsyncSession],
) -> FinalizeResult:
    """Record a failure or cancellation without overwriting a terminal outcome."""
    normalized = (
        outcome
        if isinstance(outcome, VerificationAttemptOutcome)
        else VerificationAttemptOutcome(outcome)
    )
    return await _finalize(
        attempt_id,
        session_maker=session_maker,
        outcome=normalized,
        error_code=error_code,
        validation_message=validation_message,
        terminal_source=terminal_source,
        feedback_json=None,
    )


async def expire_verification_attempts(
    *,
    queued_before: datetime,
    started_before: datetime,
    session_maker: async_sessionmaker[AsyncSession],
) -> None:
    """Expire abandoned work without rerunning it or overwriting results."""
    results: list[FinalizeResult] = []
    async with session_maker() as db:
        repo = VerificationAttemptRepository(db)
        attempts = await repo.lock_overdue(
            queued_before=queued_before, started_before=started_before
        )
        for attempt in attempts:
            results.append(
                await repo.finalize(
                    attempt.id,
                    outcome=VerificationAttemptOutcome.SERVER_ERROR,
                    error_code="verification_timeout",
                    validation_message=(
                        "Verification could not finish. This attempt was not counted. "
                        "Please try again."
                    ),
                    terminal_source="api_worker",
                    feedback_json=None,
                )
            )
        await db.commit()
    for attempt, result in zip(attempts, results, strict=True):
        if result.won:
            started = attempt.started_at
            completed_at = result.state.completed_at
            if completed_at is None:
                raise RuntimeError("A finalized attempt must have a completion time")
            logger.warning(
                "verification.attempt.stuck",
                extra={
                    "verification.attempt.id": str(attempt.id),
                    "verification.attempt.age_seconds": int(
                        (completed_at - (started or attempt.created_at)).total_seconds()
                    ),
                    "verification.stuck.reason": (
                        "execution_beyond_limit" if started else "queued_beyond_limit"
                    ),
                },
            )
        _log_canonical_completion(result)


async def _finalize(
    attempt_id: UUID,
    *,
    session_maker: async_sessionmaker[AsyncSession],
    outcome: VerificationAttemptOutcome,
    error_code: str,
    validation_message: str | None,
    terminal_source: str,
    feedback_json: list[dict] | None,
) -> FinalizeResult:
    async with session_maker() as db:
        repo = VerificationAttemptRepository(db)
        result = await repo.finalize(
            attempt_id,
            outcome=outcome,
            error_code=error_code,
            validation_message=validation_message,
            terminal_source=terminal_source,
            feedback_json=feedback_json,
        )
        await db.commit()
    _log_canonical_completion(result)
    return result


def _log_canonical_completion(result: FinalizeResult) -> None:
    if not result.won:
        return
    state = result.state
    extra: dict[str, object] = {
        "verification.attempt.id": str(state.id),
        "verification.outcome": state.outcome,
        "verification.error.code": state.error_code,
        "verification.terminal.source": state.terminal_source,
    }
    log = (
        logger.warning
        if state.outcome == VerificationAttemptOutcome.SERVER_ERROR.value
        else logger.info
    )
    log("verification.attempt.completed", extra=extra)
