"""Execute persisted verification jobs outside the FastAPI request path.

PR4 removed the legacy ``status`` enum and the ``mark_*`` lifecycle
writes. A verification job is now identified by the presence of its row
in ``verification_jobs``; the outcome lives entirely in the linked
``Submission``. The executor:

1. ``prepare_verification_job`` loads the job and, if it already has a
   linked Submission (Durable replay after a successful prior run),
   returns the same execution result without doing more work.
2. ``run_verification`` runs the validator (no DB writes).
3. ``persist_verification_result`` writes the ``Submission`` and links
   it to the job via ``VerificationJobRepository.link_submission``.
   Idempotent against retries via the ``ALREADY_LINKED`` short-circuit.

The missing-requirement edge case writes a server-error ``Submission``
and links it, so ``prepare`` stays idempotent on retry — the row exists,
the link exists, and ``preparation.terminal_result`` is reconstructed
from the linked Submission.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from uuid import UUID

from opentelemetry import trace
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from learn_to_cloud_shared.models import (
    Submission,
    User,
    VerificationJob,
)
from learn_to_cloud_shared.repositories.submission_repository import (
    SubmissionRepository,
)
from learn_to_cloud_shared.repositories.verification_job_repository import (
    LinkResult,
    VerificationJobRepository,
)
from learn_to_cloud_shared.schemas import (
    HandsOnRequirement,
    HandsOnRequirementAdapter,
    ValidationResult,
)
from learn_to_cloud_shared.verification.dispatcher import validate_submission
from learn_to_cloud_shared.verification.execution import (
    persist_validation_result,
    persisted_validation_message,
)
from learn_to_cloud_shared.verification.requirements import (
    get_requirement_by_uuid,
)

tracer = trace.get_tracer(__name__)

VALIDATION_FAILED_ERROR_CODE = "validation_failed"
VERIFICATION_INCOMPLETE_ERROR_CODE = "verification_incomplete"
REQUIREMENT_NOT_FOUND_ERROR_CODE = "requirement_not_found"
VERIFICATION_SUCCEEDED_CODE = "verification_succeeded"

# Plain string outcomes kept for Durable activity payload compatibility
# with deployed pre-PR4 readers. ``status`` consumers expect one of these
# literals.
_OUTCOME_SUCCEEDED = "succeeded"
_OUTCOME_FAILED = "failed"
_OUTCOME_SERVER_ERROR = "server_error"

_MESSAGE_BY_OUTCOME = {
    _OUTCOME_SUCCEEDED: "Verification succeeded.",
    _OUTCOME_FAILED: "Verification failed.",
    _OUTCOME_SERVER_ERROR: "Verification could not be completed.",
}


class VerificationJobNotFoundError(Exception):
    """Raised when a verification job ID does not exist."""


@dataclass(frozen=True, slots=True)
class VerificationJobExecutionResult:
    """Result of running one persisted verification job.

    ``status`` is a plain string (``"succeeded"`` / ``"failed"`` /
    ``"server_error"``) rather than the legacy ``VerificationJobStatus``
    enum so Durable activity payloads stay compatible with any pre-PR4
    readers still in flight.
    """

    job_id: UUID
    status: str
    code: str
    requirement_slug: str
    requirement_name: str | None
    submission_type: str | None
    submission_id: int | None
    is_valid: bool
    verification_completed: bool
    message: str
    detail: str | None = None

    def to_payload(self) -> dict[str, object]:
        """Return a JSON-serializable Durable activity result."""
        return {
            "job_id": str(self.job_id),
            "status": self.status,
            "code": self.code,
            "requirement_slug": self.requirement_slug,
            "requirement_name": self.requirement_name,
            "submission_type": self.submission_type,
            "submission_id": self.submission_id,
            "is_valid": self.is_valid,
            "verification_completed": self.verification_completed,
            "message": self.message,
            "detail": self.detail,
        }


@dataclass(frozen=True, slots=True)
class PreparedVerificationJob:
    """Serializable verification job input for workflow activities."""

    id: UUID
    user_id: int
    github_username: str | None
    requirement: HandsOnRequirement
    submitted_value: str

    def to_payload(self) -> dict[str, object]:
        """Return a JSON-serializable activity payload."""
        return {
            "id": str(self.id),
            "user_id": self.user_id,
            "github_username": self.github_username,
            "requirement": self.requirement.model_dump(mode="json"),
            "submitted_value": self.submitted_value,
        }

    @classmethod
    def from_payload(cls, payload: Mapping[str, object]) -> PreparedVerificationJob:
        """Rehydrate a prepared job from a Durable activity payload."""
        github_username = payload.get("github_username")
        return cls(
            id=UUID(_expect_str(payload["id"], "id")),
            user_id=_expect_int(payload["user_id"], "user_id"),
            github_username=(
                _expect_str(github_username, "github_username")
                if github_username is not None
                else None
            ),
            requirement=HandsOnRequirementAdapter.validate_python(
                payload["requirement"]
            ),
            submitted_value=_expect_str(payload["submitted_value"], "submitted_value"),
        )


@dataclass(frozen=True, slots=True)
class VerificationJobPreparation:
    """Result of preparing a verification job for execution."""

    job: PreparedVerificationJob | None = None
    terminal_result: VerificationJobExecutionResult | None = None

    def to_payload(self) -> dict[str, object]:
        """Return a JSON-serializable activity payload."""
        return {
            "job": self.job.to_payload() if self.job is not None else None,
            "terminal_result": (
                self.terminal_result.to_payload()
                if self.terminal_result is not None
                else None
            ),
        }


@dataclass(frozen=True, slots=True)
class VerificationRunResult:
    """Serializable validation result for a prepared verification job."""

    job: PreparedVerificationJob
    validation_result: ValidationResult

    def to_payload(self) -> dict[str, object]:
        """Return a JSON-serializable activity payload."""
        return {
            "job": self.job.to_payload(),
            "validation_result": self.validation_result.model_dump(mode="json"),
        }

    @classmethod
    def from_payload(cls, payload: Mapping[str, object]) -> VerificationRunResult:
        """Rehydrate a validation result from a Durable activity payload."""
        return cls(
            job=PreparedVerificationJob.from_payload(_expect_mapping(payload["job"])),
            validation_result=ValidationResult.model_validate(
                payload["validation_result"]
            ),
        )


@dataclass(frozen=True, slots=True)
class _VerificationJobPayload:
    id: UUID
    user_id: int
    github_username: str | None
    requirement_uuid: UUID
    submitted_value: str
    result_submission_id: int | None


def _expect_mapping(value: object) -> Mapping[str, object]:
    if not isinstance(value, Mapping):
        raise TypeError("Expected payload object")
    payload: dict[str, object] = {}
    for key, item in value.items():
        if not isinstance(key, str):
            raise TypeError("Expected string payload keys")
        payload[key] = item
    return payload


def _expect_int(value: object, field_name: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool):
        raise TypeError(f"Expected integer payload field: {field_name}")
    return value


def _expect_str(value: object, field_name: str) -> str:
    if not isinstance(value, str):
        raise TypeError(f"Expected string payload field: {field_name}")
    return value


def _coerce_job_id(job_id: UUID | str) -> UUID:
    if isinstance(job_id, UUID):
        return job_id
    return UUID(job_id)


async def _load_job_payload(
    db: AsyncSession,
    job_id: UUID,
) -> _VerificationJobPayload | None:
    result = await db.execute(
        select(VerificationJob, User.github_username)
        .join(User, VerificationJob.user_id == User.id)
        .where(VerificationJob.id == job_id)
    )
    row = result.one_or_none()
    if row is None:
        return None

    job, github_username = row
    return _VerificationJobPayload(
        id=job.id,
        user_id=job.user_id,
        github_username=github_username,
        requirement_uuid=job.requirement_uuid,
        submitted_value=job.submitted_value,
        result_submission_id=job.result_submission_id,
    )


def _outcome_for(validation_result: ValidationResult) -> str:
    if validation_result.is_valid:
        return _OUTCOME_SUCCEEDED
    if validation_result.verification_completed:
        return _OUTCOME_FAILED
    return _OUTCOME_SERVER_ERROR


def _code_for_outcome(outcome: str, fallback: str | None = None) -> str:
    if outcome == _OUTCOME_SUCCEEDED:
        return VERIFICATION_SUCCEEDED_CODE
    if outcome == _OUTCOME_FAILED:
        return fallback or VALIDATION_FAILED_ERROR_CODE
    return fallback or VERIFICATION_INCOMPLETE_ERROR_CODE


def _outcome_from_submission(submission: Submission) -> str:
    if submission.is_validated:
        return _OUTCOME_SUCCEEDED
    if submission.verification_completed:
        return _OUTCOME_FAILED
    return _OUTCOME_SERVER_ERROR


def _build_result_from_submission(
    *,
    job_id: UUID,
    submission: Submission,
    requirement: HandsOnRequirement | None,
    requirement_slug_fallback: str | None = None,
) -> VerificationJobExecutionResult:
    """Build a ``VerificationJobExecutionResult`` from an already-persisted
    ``Submission``. Used by the replay short-circuit in
    :func:`prepare_verification_job` and :func:`persist_verification_result`.

    When ``requirement`` is None (active lookup didn't find it -- the
    requirement was soft-deleted), the caller passes the legacy
    ``requirement_slug_fallback`` so the result payload still surfaces
    something useful in templates.
    """
    outcome = _outcome_from_submission(submission)
    requirement_slug = (
        requirement.slug
        if requirement is not None
        else (requirement_slug_fallback or "")
    )
    submission_type = (
        requirement.submission_type.value if requirement is not None else None
    )
    requirement_name = requirement.name if requirement is not None else None
    return VerificationJobExecutionResult(
        job_id=job_id,
        status=outcome,
        code=_code_for_outcome(outcome),
        requirement_slug=requirement_slug,
        requirement_name=requirement_name,
        submission_type=submission_type,
        submission_id=submission.id,
        is_valid=submission.is_validated,
        verification_completed=submission.verification_completed,
        message=_MESSAGE_BY_OUTCOME[outcome],
        detail=submission.validation_message,
    )


async def _load_requirement_metadata(
    db: AsyncSession, requirement_uuid: UUID
) -> tuple[str, str] | None:
    """Return ``(requirement_slug, submission_type)`` for a requirement by UUID,
    even if it has been soft-deleted.

    Used by the missing-requirement path to fill in the slug field on
    a server-error result when the active ``get_requirement_by_slug``
    lookup returns None.
    """
    result = await db.execute(
        text(
            "SELECT slug, submission_type FROM requirements WHERE uuid = :uuid LIMIT 1"
        ),
        {"uuid": requirement_uuid},
    )
    row = result.first()
    return (row[0], row[1]) if row else None


async def _find_requirement_by_uuid(
    db: AsyncSession, requirement_uuid: UUID
) -> HandsOnRequirement | None:
    """Return the active ``HandsOnRequirement`` matching the given UUID.

    Walks the loaded curriculum tree -- the curriculum is small enough
    (~10 requirements) that an explicit lookup map per call is cheaper
    than a JOIN through ``requirements``. Soft-deleted requirements
    return None here; callers fall back to ``_load_requirement_metadata``
    for the legacy id/submission_type when they need to render a
    server-error result.
    """
    return await get_requirement_by_uuid(db, requirement_uuid)


async def _handle_missing_requirement(
    *,
    session_maker: async_sessionmaker[AsyncSession],
    payload: _VerificationJobPayload,
) -> VerificationJobExecutionResult:
    """Record a server-error ``Submission`` for a job whose requirement was
    soft-deleted from content, link the job to it, and return the
    resulting execution result.

    Linking the Submission (rather than deleting the job row) keeps
    ``prepare_verification_job`` idempotent: a retry sees the linked
    row and short-circuits via the replay path. The FK on
    ``verification_jobs.requirement_uuid`` is ON DELETE RESTRICT, so
    the requirement row always still exists in the ``requirements``
    table -- the active read just filters out soft-deleted entries.
    The fallback metadata lookup below pulls ``id`` and
    ``submission_type`` even from soft-deleted rows for the
    server-error payload.
    """
    async with session_maker() as db:
        metadata = await _load_requirement_metadata(db, payload.requirement_uuid)
        requirement_slug_fallback = metadata[0] if metadata is not None else ""
        submission_type_fallback = metadata[1] if metadata is not None else None
        detail = f"Requirement not found: {requirement_slug_fallback}"

        submission_repo = SubmissionRepository(db)
        submission = await submission_repo.create(
            user_id=payload.user_id,
            requirement_uuid=payload.requirement_uuid,
            submitted_value=payload.submitted_value,
            extracted_username=None,
            is_validated=False,
            verification_completed=False,
            validation_message=detail,
        )
        link = await VerificationJobRepository(db).link_submission(
            payload.id,
            submission.id,
        )
        if link is LinkResult.MISSING:
            raise VerificationJobNotFoundError(str(payload.id))
        await db.commit()

    return VerificationJobExecutionResult(
        job_id=payload.id,
        status=_OUTCOME_SERVER_ERROR,
        code=REQUIREMENT_NOT_FOUND_ERROR_CODE,
        requirement_slug=requirement_slug_fallback,
        requirement_name=None,
        submission_type=submission_type_fallback,
        submission_id=submission.id,
        is_valid=False,
        verification_completed=False,
        message=_MESSAGE_BY_OUTCOME[_OUTCOME_SERVER_ERROR],
        detail=detail,
    )


async def prepare_verification_job(
    job_id: UUID | str,
    *,
    session_maker: async_sessionmaker[AsyncSession],
) -> VerificationJobPreparation:
    """Load a verification job and dispatch to the right execution path.

    Replay-safe short-circuits:
    1. If the job is already linked to a ``Submission`` (Durable retried
       prepare after the persist activity already finished), return the
       same execution result from the linked Submission.
    2. If the requirement was removed from content between submit and
       execute, record a server-error Submission and short-circuit.
    """
    normalized_job_id = _coerce_job_id(job_id)

    with tracer.start_as_current_span(
        "prepare_verification_job",
        attributes={"verification.job_id": str(normalized_job_id)},
    ) as span:
        async with session_maker() as db:
            payload = await _load_job_payload(db, normalized_job_id)
            if payload is None:
                raise VerificationJobNotFoundError(str(normalized_job_id))

            requirement = await _find_requirement_by_uuid(db, payload.requirement_uuid)

            if payload.result_submission_id is not None:
                submission = await db.get(Submission, payload.result_submission_id)
                if submission is None:
                    raise VerificationJobNotFoundError(
                        f"job {normalized_job_id} references missing submission "
                        f"{payload.result_submission_id}"
                    )
                fallback = None
                if requirement is None:
                    metadata = await _load_requirement_metadata(
                        db, payload.requirement_uuid
                    )
                    fallback = metadata[0] if metadata is not None else None
                result = _build_result_from_submission(
                    job_id=normalized_job_id,
                    submission=submission,
                    requirement=requirement,
                    requirement_slug_fallback=fallback,
                )
                span.set_attribute("verification.status", result.status)
                span.set_attribute("verification.replay", True)
                return VerificationJobPreparation(terminal_result=result)

        if requirement is None:
            result = await _handle_missing_requirement(
                session_maker=session_maker,
                payload=payload,
            )
            span.set_attribute("verification.status", result.status)
            return VerificationJobPreparation(terminal_result=result)

        return VerificationJobPreparation(
            job=PreparedVerificationJob(
                id=payload.id,
                user_id=payload.user_id,
                github_username=payload.github_username,
                requirement=requirement,
                submitted_value=payload.submitted_value,
            )
        )


async def run_verification(
    job: PreparedVerificationJob,
) -> VerificationRunResult:
    """Run the requirement validator without writing database state."""
    with tracer.start_as_current_span(
        "run_verification",
        attributes={
            "verification.job_id": str(job.id),
            "requirement.slug": job.requirement.slug,
            "submission.type": job.requirement.submission_type.value,
        },
    ) as span:
        validation_result = await validate_submission(
            requirement=job.requirement,
            submitted_value=job.submitted_value,
            expected_username=job.github_username,
        )
        span.set_attribute("verification.is_valid", validation_result.is_valid)
        span.set_attribute(
            "verification.completed",
            validation_result.verification_completed,
        )
        return VerificationRunResult(job=job, validation_result=validation_result)


async def persist_verification_result(
    run_result: VerificationRunResult,
    *,
    session_maker: async_sessionmaker[AsyncSession],
) -> VerificationJobExecutionResult:
    """Persist a validation result and link it to the verification job.

    Idempotent against Durable activity retries via the
    ``result_submission_id`` short-circuit and the
    :class:`~learn_to_cloud_shared.repositories.verification_job_repository.LinkResult.ALREADY_LINKED`
    case from ``link_submission``.
    """
    job = run_result.job
    validation_result = run_result.validation_result

    with tracer.start_as_current_span(
        "persist_verification_result",
        attributes={"verification.job_id": str(job.id)},
    ) as span:
        async with session_maker() as db:
            payload = await _load_job_payload(db, job.id)
            if payload is None:
                raise VerificationJobNotFoundError(str(job.id))

            if payload.result_submission_id is not None:
                submission = await db.get(Submission, payload.result_submission_id)
                if submission is None:
                    raise VerificationJobNotFoundError(
                        f"job {job.id} references missing submission "
                        f"{payload.result_submission_id}"
                    )
                result = _build_result_from_submission(
                    job_id=job.id,
                    submission=submission,
                    requirement=job.requirement,
                )
                span.set_attribute("verification.status", result.status)
                span.set_attribute("verification.replay", True)
                return result

            submission = await persist_validation_result(
                db,
                user_id=job.user_id,
                requirement=job.requirement,
                submitted_value=job.submitted_value,
                github_username=job.github_username,
                validation_result=validation_result,
            )

            link = await VerificationJobRepository(db).link_submission(
                job.id,
                submission.id,
            )
            if link is LinkResult.MISSING:
                raise VerificationJobNotFoundError(str(job.id))
            if link is LinkResult.ALREADY_LINKED:
                # Another activity attempt linked a Submission between our
                # _load_job_payload and the link_submission UPDATE. Roll
                # back our duplicate insert by aborting the transaction;
                # reload the canonical Submission and return its result.
                await db.rollback()
                async with session_maker() as fresh_db:
                    canonical = await _load_job_payload(fresh_db, job.id)
                    if canonical is None or canonical.result_submission_id is None:
                        raise VerificationJobNotFoundError(str(job.id))
                    canonical_submission = await fresh_db.get(
                        Submission,
                        canonical.result_submission_id,
                    )
                    if canonical_submission is None:
                        raise VerificationJobNotFoundError(str(job.id))
                    result = _build_result_from_submission(
                        job_id=job.id,
                        submission=canonical_submission,
                        requirement=job.requirement,
                    )
                span.set_attribute("verification.status", result.status)
                span.set_attribute("verification.replay", True)
                return result

            await db.commit()

        outcome = _outcome_for(validation_result)
        code = _code_for_outcome(outcome)
        span.set_attribute("verification.status", outcome)
        return VerificationJobExecutionResult(
            job_id=job.id,
            status=outcome,
            code=code,
            requirement_slug=job.requirement.slug,
            requirement_name=job.requirement.name,
            submission_type=job.requirement.submission_type.value,
            submission_id=submission.id,
            is_valid=validation_result.is_valid,
            verification_completed=validation_result.verification_completed,
            message=_MESSAGE_BY_OUTCOME[outcome],
            detail=persisted_validation_message(validation_result.message)
            if not validation_result.is_valid
            else None,
        )


async def execute_verification_job(
    job_id: UUID | str,
    *,
    session_maker: async_sessionmaker[AsyncSession],
) -> VerificationJobExecutionResult:
    """Run one persisted verification job end-to-end."""
    normalized_job_id = _coerce_job_id(job_id)

    with tracer.start_as_current_span(
        "execute_verification_job",
        attributes={"verification.job_id": str(normalized_job_id)},
    ) as span:
        preparation = await prepare_verification_job(
            normalized_job_id,
            session_maker=session_maker,
        )
        if preparation.terminal_result is not None:
            span.set_attribute(
                "verification.status",
                preparation.terminal_result.status,
            )
            return preparation.terminal_result
        if preparation.job is None:
            raise VerificationJobNotFoundError(str(normalized_job_id))

        run_result = await run_verification(preparation.job)
        result = await persist_verification_result(
            run_result,
            session_maker=session_maker,
        )
        span.set_attribute("verification.status", result.status)
        return result
