"""Prepare, finalize, and terminalize unified verification attempts.

This is the bridge (PR4) counterpart to ``verification_job_executor``: it runs
against the curriculum-decoupled ``verification_attempts`` table instead of the
legacy ``verification_jobs`` + ``submissions`` pair. Every trusted input comes
from the attempt row -- the Durable input carries only the attempt id, so a
leaked function key or a buggy caller cannot smuggle in a forged requirement.

Trust boundary and idempotency:

1. :func:`prepare_verification_attempt` loads the attempt, validates its
   payload version / snapshot provenance / hash / value kind / active state,
   deserializes the stored typed requirement snapshot, and returns a
   :class:`PreparedVerificationJob` the existing verify/grade activities run
   unchanged.
2. :func:`finalize_verification_attempt` writes the terminal outcome with a
   compare-and-set (``UPDATE ... WHERE outcome IS NULL RETURNING``) so replays
   and competing finalizers never overwrite a result, then mirrors the legacy
   ``submissions`` row for a linked legacy ``verification_jobs`` so old API
   readers stay correct.
3. :func:`terminalize_verification_attempt` is the authoritative failure path
   (orchestrator/activity exception, or the stale-attempt reconciler): it
   compare-and-sets a ``server_error`` / ``cancelled`` outcome and mirrors the
   legacy submission the same idempotent way.
"""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from opentelemetry import trace
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from learn_to_cloud_shared.models import VerificationAttemptOutcome
from learn_to_cloud_shared.repositories.submission_repository import (
    SubmissionRepository,
)
from learn_to_cloud_shared.repositories.verification_attempt_repository import (
    AttemptMirrorState,
    AttemptTerminalState,
    VerificationAttemptRepository,
)
from learn_to_cloud_shared.repositories.verification_job_repository import (
    LinkResult,
    VerificationJobRepository,
)
from learn_to_cloud_shared.submission_values import (
    SubmittedValue,
    value_kind_for_submission_type,
)
from learn_to_cloud_shared.verification.execution import (
    persisted_validation_message,
)
from learn_to_cloud_shared.verification_attempt_snapshot import (
    SUPPORTED_PAYLOAD_VERSIONS,
    AttemptSnapshotError,
    validate_snapshot_integrity,
)
from learn_to_cloud_shared.verification_job_executor import (
    PreparedVerificationJob,
    VerificationRunResult,
    _code_for_outcome,
    _outcome_for,
)

tracer = trace.get_tracer(__name__)

_SNAPSHOT_SOURCE_SUBMITTED = "submitted"
_ORCHESTRATOR_TERMINAL_SOURCE = "orchestrator"


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
    """A prepared attempt ready for the verify/grade/finalize activities."""

    job: PreparedVerificationJob

    def to_payload(self) -> dict[str, object]:
        return {"job": self.job.to_payload()}


def _outcome_flags(outcome: str) -> tuple[bool, bool]:
    """Map a terminal outcome to legacy ``(is_validated, completed)`` flags."""
    is_validated = outcome == VerificationAttemptOutcome.SUCCEEDED.value
    verification_completed = outcome in (
        VerificationAttemptOutcome.SUCCEEDED.value,
        VerificationAttemptOutcome.FAILED.value,
    )
    return is_validated, verification_completed


async def prepare_verification_attempt(
    attempt_id: UUID,
    *,
    session_maker: async_sessionmaker[AsyncSession],
) -> AttemptPreparation:
    """Validate and prepare an attempt for execution.

    Loads only the granted identity/snapshot columns, then enforces every
    trust check before returning a runnable job. Any failure raises an
    :class:`AttemptPreparationError` subclass so the orchestrator converts it
    into a terminal outcome instead of leaving the attempt hanging.
    """
    with tracer.start_as_current_span(
        "prepare_verification_attempt",
        attributes={"verification.attempt.id": str(attempt_id)},
    ):
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
                            f"attempt {attempt_id} is already terminal "
                            f"({current.outcome})"
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

        submitted_value = SubmittedValue.from_kind_and_value(
            state.submission_value_kind,
            state.submitted_value,
        )
        job = PreparedVerificationJob(
            id=state.id,
            user_id=state.user_id,
            github_username=state.github_username_snapshot,
            requirement=requirement,
            submitted_value=submitted_value,
        )
        return AttemptPreparation(job=job)


async def finalize_verification_attempt(
    run_result: VerificationRunResult,
    *,
    session_maker: async_sessionmaker[AsyncSession],
) -> AttemptTerminalState:
    """Persist an attempt's real verification outcome (CAS) + legacy mirror."""
    run_result = run_result.without_evidence()
    job = run_result.job
    validation_result = run_result.validation_result
    outcome = _outcome_for(validation_result)
    error_code = _code_for_outcome(outcome)
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
        job.id,
        session_maker=session_maker,
        outcome=VerificationAttemptOutcome(outcome),
        error_code=error_code,
        validation_message=validation_message,
        terminal_source=_ORCHESTRATOR_TERMINAL_SOURCE,
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
) -> AttemptTerminalState:
    """Compare-and-set a failure/cancellation outcome + legacy mirror.

    Used by the orchestrator's exception path and the stale-attempt
    reconciler. Never overwrites an already-terminal attempt.
    """
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


async def _finalize(
    attempt_id: UUID,
    *,
    session_maker: async_sessionmaker[AsyncSession],
    outcome: VerificationAttemptOutcome,
    error_code: str,
    validation_message: str | None,
    terminal_source: str,
    feedback_json: list[dict] | None,
) -> AttemptTerminalState:
    with tracer.start_as_current_span(
        "finalize_verification_attempt",
        attributes={
            "verification.attempt.id": str(attempt_id),
            "verification.outcome": outcome.value,
        },
    ) as span:
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
        span.set_attribute("verification.cas_won", result.won)

        # Mirror the legacy submission regardless of who won the CAS: the
        # attempt is now terminal, and the mirror is independently idempotent,
        # so a crash between the CAS commit and the mirror is recovered by any
        # retry.
        await _ensure_legacy_mirror(attempt_id, session_maker=session_maker)
        return result.state


async def _ensure_legacy_mirror(
    attempt_id: UUID,
    *,
    session_maker: async_sessionmaker[AsyncSession],
) -> None:
    """Create + link the legacy submission for a terminalized attempt, once.

    No-ops when the attempt carries no ``legacy_job_id`` (a genuinely new
    submitted attempt), when the legacy job is gone, or when the job is already
    linked. The ``link_submission`` compare-and-set is the duplicate guard: if
    a competing finalizer or the legacy execution path linked first, our
    just-inserted submission is rolled back so one attempt/job never produces
    two legacy submissions.
    """
    async with session_maker() as db:
        state = await VerificationAttemptRepository(db).get_mirror_state(attempt_id)
        if state is None or state.legacy_job_id is None or state.outcome is None:
            return

        job_repo = VerificationJobRepository(db)
        job = await job_repo.get_by_id(state.legacy_job_id)
        if job is None or job.result_submission_id is not None:
            return

        submission = await _create_mirror_submission(db, state)
        link = await job_repo.link_submission(job.id, submission.id)
        if link is LinkResult.LINKED:
            await db.commit()
            return
        # Another finalizer / the legacy path won the link race: discard our
        # duplicate insert.
        await db.rollback()


async def _create_mirror_submission(db: AsyncSession, state: AttemptMirrorState):
    is_validated, verification_completed = _outcome_flags(state.outcome or "")
    submitted_value = SubmittedValue.from_kind_and_value(
        state.submission_value_kind,
        state.submitted_value,
    )
    return await SubmissionRepository(db).create(
        user_id=state.user_id,
        requirement_uuid=state.requirement_uuid,
        submitted_value=submitted_value,
        extracted_username=state.github_username_snapshot,
        is_validated=is_validated,
        verification_completed=verification_completed,
        feedback_json=state.feedback_json,
        validation_message=state.validation_message,
        cloud_provider=state.cloud_provider,
    )
