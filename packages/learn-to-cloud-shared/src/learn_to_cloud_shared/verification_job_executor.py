"""Execute persisted verification jobs outside the FastAPI request path."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from uuid import UUID

from opentelemetry import trace
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from learn_to_cloud_shared.models import (
    User,
    VerificationJob,
    VerificationJobStatus,
)
from learn_to_cloud_shared.repositories.verification_job_repository import (
    TERMINAL_JOB_STATUSES,
    VerificationJobRepository,
)
from learn_to_cloud_shared.schemas import HandsOnRequirement, ValidationResult
from learn_to_cloud_shared.verification.dispatcher import validate_submission
from learn_to_cloud_shared.verification.execution import persist_validation_result
from learn_to_cloud_shared.verification.requirements import get_requirement_by_id

tracer = trace.get_tracer(__name__)

VALIDATION_FAILED_ERROR_CODE = "validation_failed"
VERIFICATION_INCOMPLETE_ERROR_CODE = "verification_incomplete"
REQUIREMENT_NOT_FOUND_ERROR_CODE = "requirement_not_found"


class VerificationJobNotFoundError(Exception):
    """Raised when a verification job ID does not exist."""


@dataclass(frozen=True, slots=True)
class VerificationJobExecutionResult:
    job_id: UUID
    status: VerificationJobStatus
    submission_id: int | None
    is_valid: bool
    verification_completed: bool
    message: str

    def to_payload(self) -> dict[str, object]:
        """Return a JSON-serializable Durable activity result."""
        return {
            "job_id": str(self.job_id),
            "status": self.status.value,
            "submission_id": self.submission_id,
            "is_valid": self.is_valid,
            "verification_completed": self.verification_completed,
            "message": self.message,
        }


@dataclass(frozen=True, slots=True)
class PreparedVerificationJob:
    """Serializable verification job input for workflow activities."""

    id: UUID
    user_id: int
    github_username: str | None
    requirement: HandsOnRequirement
    phase_id: int
    submitted_value: str

    def to_payload(self) -> dict[str, object]:
        """Return a JSON-serializable activity payload."""
        return {
            "id": str(self.id),
            "user_id": self.user_id,
            "github_username": self.github_username,
            "requirement": self.requirement.model_dump(mode="json"),
            "phase_id": self.phase_id,
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
            requirement=HandsOnRequirement.model_validate(payload["requirement"]),
            phase_id=_expect_int(payload["phase_id"], "phase_id"),
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
    requirement_id: str
    phase_id: int
    submitted_value: str
    status: VerificationJobStatus
    result_submission_id: int | None
    error_message: str | None


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
        requirement_id=job.requirement_id,
        phase_id=job.phase_id,
        submitted_value=job.submitted_value,
        status=job.status,
        result_submission_id=job.result_submission_id,
        error_message=job.error_message,
    )


def _terminal_result(
    payload: _VerificationJobPayload,
) -> VerificationJobExecutionResult:
    return VerificationJobExecutionResult(
        job_id=payload.id,
        status=payload.status,
        submission_id=payload.result_submission_id,
        is_valid=payload.status == VerificationJobStatus.SUCCEEDED,
        verification_completed=payload.status != VerificationJobStatus.SERVER_ERROR,
        message=payload.error_message or "Verification job already completed.",
    )


async def _mark_missing_requirement(
    *,
    session_maker: async_sessionmaker[AsyncSession],
    job_id: UUID,
    requirement_id: str,
) -> VerificationJobExecutionResult:
    message = f"Requirement not found: {requirement_id}"
    async with session_maker() as db:
        job = await VerificationJobRepository(db).mark_server_error(
            job_id,
            error_code=REQUIREMENT_NOT_FOUND_ERROR_CODE,
            error_message=message,
        )
        if job is None:
            raise VerificationJobNotFoundError(str(job_id))
        await db.commit()

    return VerificationJobExecutionResult(
        job_id=job_id,
        status=VerificationJobStatus.SERVER_ERROR,
        submission_id=None,
        is_valid=False,
        verification_completed=False,
        message=message,
    )


async def prepare_verification_job(
    job_id: UUID | str,
    *,
    session_maker: async_sessionmaker[AsyncSession],
) -> VerificationJobPreparation:
    """Load and mark a verification job as running before validation."""
    normalized_job_id = _coerce_job_id(job_id)

    with tracer.start_as_current_span(
        "prepare_verification_job",
        attributes={"verification.job_id": str(normalized_job_id)},
    ) as span:
        async with session_maker() as db:
            payload = await _load_job_payload(db, normalized_job_id)
            if payload is None:
                raise VerificationJobNotFoundError(str(normalized_job_id))
            if payload.status in TERMINAL_JOB_STATUSES:
                result = _terminal_result(payload)
                span.set_attribute("verification.status", result.status.value)
                return VerificationJobPreparation(terminal_result=result)

            await VerificationJobRepository(db).mark_running(normalized_job_id)
            await db.commit()

        requirement = get_requirement_by_id(payload.requirement_id)
        if requirement is None:
            result = await _mark_missing_requirement(
                session_maker=session_maker,
                job_id=normalized_job_id,
                requirement_id=payload.requirement_id,
            )
            span.set_attribute("verification.status", result.status.value)
            return VerificationJobPreparation(terminal_result=result)

        return VerificationJobPreparation(
            job=PreparedVerificationJob(
                id=payload.id,
                user_id=payload.user_id,
                github_username=payload.github_username,
                requirement=requirement,
                phase_id=payload.phase_id,
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
            "requirement.id": job.requirement.id,
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
    """Persist a validation result and mark the verification job terminal."""
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
            if payload.status in TERMINAL_JOB_STATUSES:
                result = _terminal_result(payload)
                span.set_attribute("verification.status", result.status.value)
                return result

            submission = await persist_validation_result(
                db,
                user_id=job.user_id,
                requirement=job.requirement,
                phase_id=job.phase_id,
                submitted_value=job.submitted_value,
                github_username=job.github_username,
                validation_result=validation_result,
            )

            job_repo = VerificationJobRepository(db)
            if validation_result.is_valid:
                updated_job = await job_repo.mark_succeeded(job.id, submission.id)
                status = VerificationJobStatus.SUCCEEDED
            elif validation_result.verification_completed:
                updated_job = await job_repo.mark_failed(
                    job.id,
                    error_code=VALIDATION_FAILED_ERROR_CODE,
                    error_message=validation_result.message,
                    result_submission_id=submission.id,
                )
                status = VerificationJobStatus.FAILED
            else:
                updated_job = await job_repo.mark_server_error(
                    job.id,
                    error_code=VERIFICATION_INCOMPLETE_ERROR_CODE,
                    error_message=validation_result.message,
                    result_submission_id=submission.id,
                )
                status = VerificationJobStatus.SERVER_ERROR

            if updated_job is None:
                raise VerificationJobNotFoundError(str(job.id))

            await db.commit()

        span.set_attribute("verification.status", status.value)
        return VerificationJobExecutionResult(
            job_id=job.id,
            status=status,
            submission_id=submission.id,
            is_valid=validation_result.is_valid,
            verification_completed=validation_result.verification_completed,
            message=validation_result.message,
        )


async def execute_verification_job(
    job_id: UUID | str,
    *,
    session_maker: async_sessionmaker[AsyncSession],
) -> VerificationJobExecutionResult:
    """Run one persisted verification job and update its DB status."""
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
                preparation.terminal_result.status.value,
            )
            return preparation.terminal_result
        if preparation.job is None:
            raise VerificationJobNotFoundError(str(normalized_job_id))

        run_result = await run_verification(preparation.job)
        result = await persist_verification_result(
            run_result,
            session_maker=session_maker,
        )
        span.set_attribute("verification.status", result.status.value)
        return result
