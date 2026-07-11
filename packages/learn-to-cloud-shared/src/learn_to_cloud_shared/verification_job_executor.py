"""Execute persisted verification jobs outside the FastAPI request path.

A verification job is identified by the presence of its row in
``verification_jobs``; the outcome lives entirely in the linked
``Submission``. The executor:

1. ``prepare_verification_job`` validates the persisted job against the
   orchestration's ``PreparedVerificationJob`` payload and, if the job
   already has a linked Submission (Durable replay after a successful
   prior run), returns the same execution result without doing more
   work.
2. ``run_verification`` runs the validator (no DB writes).
3. ``persist_verification_result`` writes the ``Submission`` and links
   it to the job via ``VerificationJobRepository.link_submission``.
   Idempotent against retries via the ``ALREADY_LINKED`` short-circuit.

The requirement definition and ``github_username`` snapshot travel with
the orchestration payload, so the executor never reads ``users`` or any
curriculum table. A soft-delete of the requirement between submit and
execute is invisible here: validation runs against the submit-time
snapshot.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, replace
from uuid import UUID

from opentelemetry import trace
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from learn_to_cloud_shared.github_target import GitHubTarget
from learn_to_cloud_shared.models import (
    Submission,
    VerificationJob,
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
from learn_to_cloud_shared.submission_derivation import build_target
from learn_to_cloud_shared.submission_values import (
    SubmittedValue,
    submission_value_from_columns,
)
from learn_to_cloud_shared.verification.dispatcher import (
    validate_submission,
)
from learn_to_cloud_shared.verification.execution import (
    persist_validation_result,
)
from learn_to_cloud_shared.verification.tasks.base import EvidenceBundle

tracer = trace.get_tracer(__name__)

VALIDATION_FAILED_ERROR_CODE = "validation_failed"
VERIFICATION_INCOMPLETE_ERROR_CODE = "verification_incomplete"
REQUIREMENT_NOT_FOUND_ERROR_CODE = "requirement_not_found"
VERIFICATION_SUCCEEDED_CODE = "verification_succeeded"

# Plain string outcomes carried on the Durable activity payload. ``status``
# consumers expect one of these literals.
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
    ``"server_error"``) so Durable activity payloads carry a stable literal
    rather than an enum.
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
        }


@dataclass(frozen=True, slots=True)
class PreparedVerificationJob:
    """Serializable verification job input for workflow activities."""

    id: UUID
    user_id: int
    github_username: str | None
    requirement: HandsOnRequirement
    submitted_value: SubmittedValue | str

    def __post_init__(self) -> None:
        if isinstance(self.submitted_value, str):
            object.__setattr__(
                self,
                "submitted_value",
                SubmittedValue.from_raw(self.requirement, self.submitted_value),
            )

    def to_payload(self) -> dict[str, object]:
        """Return a JSON-serializable activity payload."""
        return {
            "id": str(self.id),
            "user_id": self.user_id,
            "github_username": self.github_username,
            "requirement": self.requirement.model_dump(mode="json"),
            "submitted_value": self.typed_submitted_value.as_text,
            "submission_value": self.typed_submitted_value.to_payload(),
        }

    @property
    def typed_submitted_value(self) -> SubmittedValue:
        if isinstance(self.submitted_value, str):
            return SubmittedValue.from_raw(self.requirement, self.submitted_value)
        return self.submitted_value

    @property
    def target(self) -> GitHubTarget | None:
        """The GitHub location this job verifies against.

        Constructed from the requirement plus the ``github_username`` snapshot,
        both already on the payload, so every activity derives the same
        identity without carrying or re-parsing it. ``None`` for free-form
        types that reference no GitHub location.
        """
        return build_target(self.requirement, self.github_username)

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
            submitted_value=(
                SubmittedValue.from_payload(payload["submission_value"])
                if "submission_value" in payload
                else SubmittedValue.from_raw(
                    HandsOnRequirementAdapter.validate_python(payload["requirement"]),
                    _expect_str(payload["submitted_value"], "submitted_value"),
                )
            ),
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
    """Serializable validation result for a prepared verification job.

    ``evidence`` carries the :class:`EvidenceBundle`s gathered by the engine's
    steps so grading can read file contents without re-fetching. It is
    round-tripped between activities but stripped before the terminal DB write
    (see :meth:`without_evidence`) so file contents never reach Postgres.
    Defaults to ``None`` for the legacy path that gathers no evidence.
    """

    job: PreparedVerificationJob
    validation_result: ValidationResult
    evidence: list[EvidenceBundle] | None = None

    def to_payload(self) -> dict[str, object]:
        """Return a JSON-serializable activity payload."""
        return {
            "job": self.job.to_payload(),
            "validation_result": self.validation_result.model_dump(mode="json"),
            "evidence": (
                [bundle.model_dump(mode="json") for bundle in self.evidence]
                if self.evidence is not None
                else None
            ),
        }

    @classmethod
    def from_payload(cls, payload: Mapping[str, object]) -> VerificationRunResult:
        """Rehydrate a validation result from a Durable activity payload."""
        raw_evidence = payload.get("evidence")
        evidence = (
            [EvidenceBundle.model_validate(bundle) for bundle in raw_evidence]
            if isinstance(raw_evidence, list)
            else None
        )
        return cls(
            job=PreparedVerificationJob.from_payload(_expect_mapping(payload["job"])),
            validation_result=ValidationResult.model_validate(
                payload["validation_result"]
            ),
            evidence=evidence,
        )

    def without_evidence(self) -> VerificationRunResult:
        """Return a copy with evidence dropped, for the terminal DB write."""
        if self.evidence is None:
            return self
        return replace(self, evidence=None)


@dataclass(frozen=True, slots=True)
class _VerificationJobPayload:
    id: UUID
    user_id: int
    requirement_uuid: UUID
    submitted_value: SubmittedValue
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
    requirement: HandsOnRequirement,
) -> VerificationJobExecutionResult:
    """Build a ``VerificationJobExecutionResult`` from an already-persisted
    ``Submission``. Used by the replay short-circuit in
    :func:`prepare_verification_job` and :func:`persist_verification_result`.

    The requirement is always available (carried on the orchestration
    payload) so we don't need a soft-delete fallback shape.
    """
    outcome = _outcome_from_submission(submission)
    return VerificationJobExecutionResult(
        job_id=job_id,
        status=outcome,
        code=_code_for_outcome(outcome),
        requirement_slug=requirement.slug,
        requirement_name=requirement.name,
        submission_type=requirement.submission_type.value,
        submission_id=submission.id,
        is_valid=submission.is_validated,
        verification_completed=submission.verification_completed,
        message=_MESSAGE_BY_OUTCOME[outcome],
    )


async def prepare_verification_job(
    job_id: UUID | str,
    *,
    session_maker: async_sessionmaker[AsyncSession],
    prepared_input: PreparedVerificationJob,
) -> VerificationJobPreparation:
    """Preflight a verification job: anti-forgery identity check + replay guard.

    The orchestration always carries a full ``PreparedVerificationJob``
    payload (curriculum-decoupling refactor). This activity is the trust
    boundary and idempotency gate for the run:

    1. **Anti-forgery identity check.** Loads the ``verification_jobs`` row and
       asserts the payload's immutable identity fields (``user_id``,
       ``requirement_uuid``, ``submitted_value``) match it. The requirement
       *definition* and ``github_username`` snapshot are trusted from the
       payload (the Functions role has no curriculum/users grants), so this
       row match is what stops a forged or buggy start request from running
       validation against an arbitrary user or requirement.
    2. **Replay/idempotency short-circuit.** Durable retries an activity on a
       transient fault and resumes it after a worker crash, so this can run
       more than once for the same job. If the job is already linked to a
       ``Submission`` (the persist activity already finished on a prior
       attempt), it returns that same execution result instead of re-running,
       so retries never produce a second outcome.
    3. Otherwise returns the prepared job for the orchestrator to run.

    The Functions role only needs ``SELECT`` on ``verification_jobs`` +
    ``submissions`` here -- no curriculum or users reads.
    """
    normalized_job_id = _coerce_job_id(job_id)

    with tracer.start_as_current_span(
        "prepare_verification_job",
        attributes={"verification.job.id": str(normalized_job_id)},
    ) as span:
        async with session_maker() as db:
            payload = await _load_job_state(db, normalized_job_id)
            if payload is None:
                raise VerificationJobNotFoundError(str(normalized_job_id))
            if (
                payload.user_id != prepared_input.user_id
                or payload.requirement_uuid != prepared_input.requirement.uuid
                or payload.submitted_value != prepared_input.typed_submitted_value
            ):
                raise VerificationJobNotFoundError(
                    f"prepared payload does not match verification_jobs "
                    f"row for job {normalized_job_id}"
                )
            requirement = prepared_input.requirement

            if payload.result_submission_id is not None:
                submission = await db.get(Submission, payload.result_submission_id)
                if submission is None:
                    raise VerificationJobNotFoundError(
                        f"job {normalized_job_id} references missing submission "
                        f"{payload.result_submission_id}"
                    )
                result = _build_result_from_submission(
                    job_id=normalized_job_id,
                    submission=submission,
                    requirement=requirement,
                )
                span.set_attribute("verification.status", result.status)
                span.set_attribute("verification.replay", True)
                return VerificationJobPreparation(terminal_result=result)

        return VerificationJobPreparation(
            job=PreparedVerificationJob(
                id=payload.id,
                user_id=payload.user_id,
                github_username=prepared_input.github_username,
                requirement=requirement,
                submitted_value=payload.submitted_value,
            )
        )


async def _load_job_state(
    db: AsyncSession,
    job_id: UUID,
) -> _VerificationJobPayload | None:
    """Load the verification_jobs row's identity + replay state.

    No JOIN against ``users`` -- the ``github_username`` snapshot
    travels with the orchestration payload after the curriculum-
    decoupling refactor, so the Functions role doesn't need
    ``SELECT ON users`` and this query is one indexed PK lookup.
    """
    job = await db.get(VerificationJob, job_id)
    if job is None:
        return None
    return _VerificationJobPayload(
        id=job.id,
        user_id=job.user_id,
        requirement_uuid=job.requirement_uuid,
        submitted_value=submission_value_from_columns(job),
        result_submission_id=job.result_submission_id,
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
            submitted_value=job.typed_submitted_value.as_text,
            target=job.target,
            expected_username=job.github_username,
        )
        span.set_attribute("verification.is_valid", validation_result.is_valid)
        span.set_attribute(
            "verification.completed",
            validation_result.verification_completed,
        )
        return VerificationRunResult(
            job=job,
            validation_result=validation_result,
        )


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
            payload = await _load_job_state(db, job.id)
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
                submitted_value=job.typed_submitted_value,
                target=job.target,
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
                # _load_job_state and the link_submission UPDATE. Roll
                # back our duplicate insert by aborting the transaction;
                # reload the canonical Submission and return its result.
                await db.rollback()
                async with session_maker() as fresh_db:
                    canonical = await _load_job_state(fresh_db, job.id)
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
        )


async def execute_verification_job(
    job_id: UUID | str,
    *,
    session_maker: async_sessionmaker[AsyncSession],
    prepared_input: PreparedVerificationJob,
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
            prepared_input=prepared_input,
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
