"""The declarative verification engine.

Plain shared-package code (no Durable imports) that the Durable activities
call. A submission type maps to a :class:`VerificationProfile`: an ordered
list of :class:`Step`s, each naming a registered **check** (code) plus typed
**params** (data). :func:`run_profile` looks up the profile, runs its steps in
order, short-circuits on a failed gate, accumulates
:class:`EvidenceBundle`s, and produces one aggregate ``ValidationResult``.

Checks are registered by name in ``_CHECK_REGISTRY`` via
:func:`register_check`. Adding a verification behavior becomes "register a
check, declare a profile," not "touch an orchestrator and a validator."

Transitional: submission types that have not been migrated to a declared
profile run a single ``legacy_validate`` step backed by
``validate_submission`` (the per-type dispatcher). That fallthrough and this
note are removed once every type resolves to a real profile.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass, replace
from typing import Literal
from uuid import UUID

from opentelemetry import trace
from pydantic import Field
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from learn_to_cloud_shared.github_target import GitHubTarget
from learn_to_cloud_shared.schemas import FrozenModel, TaskResult, ValidationResult
from learn_to_cloud_shared.verification.dispatcher import (
    ValidatorDescriptor,
    descriptor_for,
    validate_submission,
)
from learn_to_cloud_shared.verification.repo_files import RepoFiles
from learn_to_cloud_shared.verification.tasks.base import (
    EvidenceBundle,
    LLMRubricGraderConfig,
)
from learn_to_cloud_shared.verification_job_executor import (
    PreparedVerificationJob,
    VerificationJobExecutionResult,
    VerificationJobNotFoundError,
    VerificationRunResult,
    persist_verification_result,
    prepare_verification_job,
)

_tracer = trace.get_tracer(__name__)

# ---------------------------------------------------------------------------
# Step params: per-check models in a discriminated union keyed by ``check``.
# ---------------------------------------------------------------------------


class LegacyValidateParams(FrozenModel):
    """Params for the transitional ``legacy_validate`` check (no config)."""

    check: Literal["legacy_validate"] = "legacy_validate"


# The per-check discriminated union. With one member today it is a plain
# alias; as PR2+ register more checks (files_present, fetch_files,
# llm_rubric_review, ...) this becomes
# ``Annotated[LegacyValidateParams | ..., Field(discriminator="check")]``.
StepParams = LegacyValidateParams


# ---------------------------------------------------------------------------
# Engine primitives.
# ---------------------------------------------------------------------------


class Step(FrozenModel):
    """One ordered gate in a profile: a registered check plus its params.

    ``check`` is the registry key (which code runs); ``params`` is the typed
    per-check config. They are kept separate, per the engine sketch, so the
    dispatch key and the param schema evolve independently.
    """

    check: str
    params: StepParams
    task_id: str


class StepResult(FrozenModel):
    """Outcome of running one step.

    ``evidence`` is contributed to the run's bundle and made visible to later
    steps. ``stop_on_fail`` lets a failed gate short-circuit the remaining
    steps. ``validation_result`` is the transitional passthrough used by the
    ``legacy_validate`` step to carry a full dispatcher result unchanged; it is
    removed once every type is migrated to task-level results.
    """

    passed: bool
    task_result: TaskResult | None = None
    evidence: list[EvidenceBundle] = Field(default_factory=list)
    stop_on_fail: bool = True
    validation_result: ValidationResult | None = None


@dataclass(frozen=True, slots=True)
class StepContext:
    """Everything a check may read. Carries runtime clients, so not a model."""

    job: PreparedVerificationJob
    repository: GitHubTarget | None
    submitted_value: str
    evidence_so_far: tuple[EvidenceBundle, ...] = ()
    repo_files: RepoFiles | None = None


@dataclass(frozen=True)
class VerificationProfile(ValidatorDescriptor):
    """A submission type's declared workflow.

    Extends the dispatcher's :class:`ValidatorDescriptor` with an ordered step
    list and the terminal LLM step's persona/rubric. A profile with no steps
    falls back to the transitional ``legacy_validate`` step.
    """

    steps: tuple[Step, ...] = ()
    system_prompt: str | None = None
    rubric: LLMRubricGraderConfig | None = None


CheckFn = Callable[[StepContext, StepParams], Awaitable[StepResult]]

_CHECK_REGISTRY: dict[str, CheckFn] = {}


def register_check(name: str) -> Callable[[CheckFn], CheckFn]:
    """Register a check under ``name``. Raises if the name is already taken."""

    def decorator(fn: CheckFn) -> CheckFn:
        if name in _CHECK_REGISTRY:
            raise ValueError(f"Check already registered: {name}")
        _CHECK_REGISTRY[name] = fn
        return fn

    return decorator


def check_for(name: str) -> CheckFn:
    """Return the check registered under ``name`` or raise ``KeyError``."""
    try:
        return _CHECK_REGISTRY[name]
    except KeyError:
        raise KeyError(f"No check registered for {name!r}") from None


# ---------------------------------------------------------------------------
# Transitional legacy check: delegate to the per-type dispatcher.
# ---------------------------------------------------------------------------


@register_check("legacy_validate")
async def _check_legacy_validate(
    context: StepContext,
    params: StepParams,
) -> StepResult:
    """Run the per-type validator via the dispatcher (transitional)."""
    result = await validate_submission(
        requirement=context.job.requirement,
        submitted_value=context.submitted_value,
        target=context.repository,
        expected_username=context.job.github_username,
    )
    return StepResult(
        passed=result.is_valid,
        stop_on_fail=True,
        validation_result=result,
    )


_LEGACY_STEP = Step(
    check="legacy_validate",
    params=LegacyValidateParams(),
    task_id="legacy_validate",
)


def _steps_for(descriptor: ValidatorDescriptor | None) -> tuple[Step, ...]:
    """Resolve the step list, falling back to the transitional legacy step."""
    if isinstance(descriptor, VerificationProfile) and descriptor.steps:
        return descriptor.steps
    return (_LEGACY_STEP,)


def _aggregate(step_results: list[StepResult]) -> ValidationResult:
    """Fold step results into one ``ValidationResult``.

    A ``validation_result`` passthrough (the legacy step) is authoritative and
    returned unchanged. Migrated profiles aggregate from per-step task results.
    """
    for result in step_results:
        if result.validation_result is not None:
            return result.validation_result

    task_results = [r.task_result for r in step_results if r.task_result is not None]
    passed = all(r.passed for r in step_results)
    message = (
        "Verification succeeded."
        if passed
        else "Verification failed. Review the task feedback and try again."
    )
    return ValidationResult(
        is_valid=passed,
        message=message,
        task_results=task_results or None,
        verification_completed=True,
    )


async def run_profile(
    job: PreparedVerificationJob,
    *,
    repo_files: RepoFiles | None = None,
) -> VerificationRunResult:
    """Run a submission type's profile and return the aggregate result.

    Steps run in order; a failed gate with ``stop_on_fail`` short-circuits the
    rest. Evidence bundles accumulate across steps, are visible to later steps
    via ``evidence_so_far``, and are carried on the returned run result.
    """
    descriptor = descriptor_for(job.requirement.submission_type)
    steps = _steps_for(descriptor)

    context = StepContext(
        job=job,
        repository=job.target,
        submitted_value=job.typed_submitted_value.as_text,
        repo_files=repo_files,
    )

    step_results: list[StepResult] = []
    bundles: list[EvidenceBundle] = []
    for step in steps:
        result = await check_for(step.check)(context, step.params)
        step_results.append(result)
        if result.evidence:
            bundles.extend(result.evidence)
            context = replace(
                context,
                evidence_so_far=(*context.evidence_so_far, *result.evidence),
            )
        if not result.passed and result.stop_on_fail:
            break

    return VerificationRunResult(
        job=job,
        validation_result=_aggregate(step_results),
        evidence=bundles or None,
    )


async def execute_verification_job(
    job_id: UUID | str,
    *,
    session_maker: async_sessionmaker[AsyncSession],
    prepared_input: PreparedVerificationJob,
) -> VerificationJobExecutionResult:
    """Run one persisted verification job end-to-end (prepare, run, persist).

    A non-grading convenience over the individual primitives. Production
    sequences the same steps (plus grading) as separate Durable activities;
    this collapses them for callers that want a single deterministic run.
    """
    normalized_job_id = job_id if isinstance(job_id, UUID) else UUID(job_id)

    with _tracer.start_as_current_span(
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

        run_result = await run_profile(preparation.job)
        result = await persist_verification_result(
            run_result,
            session_maker=session_maker,
        )
        span.set_attribute("verification.status", result.status)
        return result
