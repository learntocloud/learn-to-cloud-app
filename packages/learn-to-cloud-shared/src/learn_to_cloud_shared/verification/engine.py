"""Execute verification workflows, record safe telemetry, and prepare grading."""

from __future__ import annotations

from dataclasses import replace

from opentelemetry import trace
from opentelemetry.trace import Status, StatusCode

from learn_to_cloud_shared.github_repository_target import GitHubRepositoryTarget
from learn_to_cloud_shared.schemas import ValidationResult
from learn_to_cloud_shared.verification.core import (
    Step,
    StepContext,
    StepResult,
    VerificationWorkflow,
)
from learn_to_cloud_shared.verification.evidence import (
    EvidenceError,
    record_evidence_decision,
    validate_evidence_bundle,
)
from learn_to_cloud_shared.verification.grading_requests import (
    LLMGradingRequest,
    build_repo_rubric_message,
    build_text_rubric_message,
)
from learn_to_cloud_shared.verification.repo_files import RepoFiles
from learn_to_cloud_shared.verification.repository_ownership import (
    check_repository_ownership,
)
from learn_to_cloud_shared.verification.tasks.base import EvidenceBundle
from learn_to_cloud_shared.verification.workflows import workflow_for
from learn_to_cloud_shared.verification_workflow import (
    GradingDisposition,
    PreparedVerificationAttempt,
    VerificationRunResult,
)

_tracer = trace.get_tracer(__name__)


def _aggregate(step_results: list[StepResult]) -> ValidationResult:
    """Fold step results into one ``ValidationResult``.

    One deterministic gate is returned unchanged. Multiple gates fold in
    declaration order: the last gate supplies the decisive message while all
    gate outcomes and task feedback contribute to the aggregate.
    """
    authoritative_results = [
        result.validation_result
        for result in step_results
        if result.validation_result is not None
    ]
    if len(authoritative_results) == 1:
        result = authoritative_results[0]
        if result.is_valid and any(not step.passed for step in step_results):
            return result.model_copy(update={"is_valid": False})
        return result
    if authoritative_results:
        incomplete_results = [
            result
            for result in authoritative_results
            if not result.verification_completed
        ]
        failed_results = [
            result for result in authoritative_results if not result.is_valid
        ]
        decisive_result = (
            incomplete_results or failed_results or authoritative_results
        )[-1]
        task_results = [
            task_result
            for validation_result in authoritative_results
            for task_result in (validation_result.task_results or [])
        ]

        def latest_value(field: str) -> bool | str | None:
            for validation_result in reversed(authoritative_results):
                value = getattr(validation_result, field)
                if value is not None:
                    return value
            return None

        return decisive_result.model_copy(
            update={
                "is_valid": all(result.is_valid for result in authoritative_results)
                and all(result.passed for result in step_results),
                "username_match": latest_value("username_match"),
                "repo_exists": latest_value("repo_exists"),
                "task_results": task_results or None,
                "verification_completed": all(
                    result.verification_completed for result in authoritative_results
                ),
                "cloud_provider": latest_value("cloud_provider"),
                "error_code": decisive_result.error_code or latest_value("error_code"),
            }
        )

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


def _grading_requests_for(
    job: PreparedVerificationAttempt,
    target: GitHubRepositoryTarget | None,
    deterministic_result: ValidationResult,
    step_results: list[StepResult],
) -> list[LLMGradingRequest]:
    """Turn steps that requested grading into recorded grading requests.

    Runs after aggregation so the prompt carries the final deterministic
    result. Incomplete verification never produces grading requests, even
    when an earlier step collected evidence before a later gate stopped the run.

    A task whose evidence source is ``submitted_text`` grades free text with no
    repository (Phase 7); every other task requires a repository target.
    """
    if (
        not deterministic_result.verification_completed
        or not deterministic_result.is_valid
        or any(not result.passed for result in step_results)
    ):
        return []
    requests: list[LLMGradingRequest] = []
    for result in step_results:
        task = result.grading_task
        if task is None:
            continue
        if len(result.evidence) != 1:
            raise EvidenceError("evidence.selection")
        validate_evidence_bundle(task, result.evidence[0])
        evidence = result.evidence[0].model_dump(mode="json") if result.evidence else {}
        allowed_evidence_refs = [
            str(item["path"])
            for item in evidence.get("items", [])
            if isinstance(item, dict) and item.get("path")
        ]
        if deterministic_result.task_results:
            allowed_evidence_refs.extend(
                task_result.task_name
                for task_result in deterministic_result.task_results
            )
        if task.evidence.source == "submitted_text":
            message = build_text_rubric_message(
                requirement_slug=job.requirement.slug,
                requirement_name=job.requirement.name,
                deterministic_result=deterministic_result,
                task=task,
                evidence=evidence,
            )
        else:
            if target is None:
                raise EvidenceError("evidence.configuration")
            message = build_repo_rubric_message(
                requirement_slug=job.requirement.slug,
                requirement_name=job.requirement.name,
                deterministic_result=deterministic_result,
                owner=target.owner,
                repo=target.repo,
                task=task,
                evidence=evidence,
            )
        requests.append(
            LLMGradingRequest(
                task=task,
                message=message,
                thread_id=f"{job.id}-{task.id}",
                allowed_evidence_refs=allowed_evidence_refs,
            )
        )
    return requests


def _grading_disposition_for(
    workflow: VerificationWorkflow,
    step_results: list[StepResult],
    grading_requests: list[LLMGradingRequest],
) -> GradingDisposition:
    """Explain why this run will or will not enter LLM grading."""
    if workflow.rubric is None:
        if grading_requests:
            raise ValueError("Non-rubric workflow produced grading requests")
        return GradingDisposition.NOT_REQUIRED
    if grading_requests:
        return GradingDisposition.REQUESTED
    if any(not result.passed for result in step_results):
        return GradingDisposition.SKIPPED_GATE_FAILED
    raise ValueError("Rubric workflow completed without a grading request")


def _step_result_state(result: StepResult) -> str:
    if result.passed:
        return "passed"
    if (
        result.validation_result is not None
        and not result.validation_result.verification_completed
    ):
        return "unavailable"
    return "failed"


def _record_step_error(span: trace.Span, exc: Exception) -> None:
    """Mark unexpected failures without exporting exception details."""
    span.set_attribute("verification.step.result", "error")
    span.set_attribute("error.type", type(exc).__name__)
    span.set_status(Status(StatusCode.ERROR))


async def _run_step(step: Step, context: StepContext) -> StepResult:
    with _tracer.start_as_current_span(
        "verification.step",
        attributes={
            "verification.check.name": step.name,
            "verification.task.id": step.task_id,
        },
        record_exception=False,
        set_status_on_exception=False,
    ) as span:
        try:
            result = await step.check(context)
            if result.grading_task is not None:
                if len(result.evidence) != 1:
                    raise EvidenceError("evidence.selection")
                validate_evidence_bundle(result.grading_task, result.evidence[0])
        except EvidenceError as exc:
            if not exc.recorded:
                record_evidence_decision(exc.code)
            result = StepResult(
                passed=False,
                stop_on_fail=True,
                validation_result=exc.to_validation_result(),
            )
        except Exception as exc:
            _record_step_error(span, exc)
            raise

        result_state = _step_result_state(result)
        span.set_attribute("verification.step.result", result_state)
        if result_state == "unavailable":
            span.set_status(Status(StatusCode.ERROR))
        return result


async def run_verification(
    job: PreparedVerificationAttempt,
    *,
    repo_files: RepoFiles | None = None,
) -> VerificationRunResult:
    """Check repository ownership, then run the assignment's verification steps.

    Steps run in order; a failed gate with ``stop_on_fail`` short-circuits the
    rest. Evidence bundles accumulate across steps, are visible to later steps
    via ``evidence_so_far``, and are carried on the returned run result.

    Every result records both its LLM grading requests and a
    ``grading_disposition`` explaining why grading was requested or skipped.
    An unregistered type (which the exhaustiveness test forbids) returns a
    clean error result.
    """
    workflow = workflow_for(job.requirement.submission_type)
    if workflow is None:
        return VerificationRunResult(
            attempt=job,
            validation_result=ValidationResult(
                is_valid=False,
                message=(f"Unknown submission type: {job.requirement.submission_type}"),
                username_match=False,
                repo_exists=False,
            ),
            evidence=None,
            grading_requests=[],
            grading_disposition=(GradingDisposition.SKIPPED_UNKNOWN_SUBMISSION_TYPE),
        )

    if workflow.requires_username and not job.github_username:
        return VerificationRunResult(
            attempt=job,
            validation_result=ValidationResult(
                is_valid=False,
                message="GitHub username is required for this verification",
                username_match=False,
            ),
            evidence=None,
            grading_requests=[],
            grading_disposition=GradingDisposition.SKIPPED_MISSING_USERNAME,
        )

    target = job.target
    if target is not None:
        with _tracer.start_as_current_span(
            "verification.step",
            attributes={"verification.check.name": "github_repository_ownership"},
            record_exception=False,
            set_status_on_exception=False,
        ) as span:
            try:
                ownership = await check_repository_ownership(target, job.user_id)
            except Exception as exc:
                _record_step_error(span, exc)
                raise
            if isinstance(ownership, ValidationResult):
                span.set_attribute(
                    "verification.step.result",
                    "failed" if ownership.verification_completed else "unavailable",
                )
                if not ownership.verification_completed:
                    span.set_status(Status(StatusCode.ERROR))
                return VerificationRunResult(
                    attempt=job,
                    validation_result=ownership,
                    grading_requests=[],
                    grading_disposition=(
                        GradingDisposition.SKIPPED_GATE_FAILED
                        if workflow.rubric is not None
                        else GradingDisposition.NOT_REQUIRED
                    ),
                )
            span.set_attribute("verification.step.result", "passed")
            target = ownership

    context = StepContext(
        job=job,
        repository=target,
        submitted_value=job.submitted_value,
        repo_files=repo_files,
    )

    step_results: list[StepResult] = []
    bundles: list[EvidenceBundle] = []
    for step in workflow.steps:
        result = await _run_step(step, context)
        step_results.append(result)
        if result.evidence:
            bundles.extend(result.evidence)
            context = replace(
                context,
                evidence_so_far=(*context.evidence_so_far, *result.evidence),
            )
        if not result.passed and result.stop_on_fail:
            break

    deterministic_result = _aggregate(step_results)
    try:
        grading_requests = _grading_requests_for(
            job, target, deterministic_result, step_results
        )
    except EvidenceError as exc:
        record_evidence_decision(exc.code)
        deterministic_result = exc.to_validation_result()
        grading_requests = []
        step_results.append(
            StepResult(
                passed=False,
                validation_result=deterministic_result,
            )
        )
    grading_disposition = _grading_disposition_for(
        workflow, step_results, grading_requests
    )

    return VerificationRunResult(
        attempt=job,
        validation_result=deterministic_result,
        evidence=bundles or None,
        grading_requests=grading_requests,
        grading_disposition=grading_disposition,
    )
