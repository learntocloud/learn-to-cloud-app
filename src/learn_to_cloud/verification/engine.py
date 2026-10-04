"""Run a submission's check, trace it, and prepare grading."""

from __future__ import annotations

from typing import assert_never

from opentelemetry import trace
from opentelemetry.trace import Status, StatusCode

from learn_to_cloud.models import SubmissionType
from learn_to_cloud.schemas.verification import ValidationResult
from learn_to_cloud.verification.attempt_types import (
    PreparedVerificationAttempt,
    VerificationRunResult,
)
from learn_to_cloud.verification.ci_status import verify_ci_status
from learn_to_cloud.verification.core import CheckResult, GradingEvidence
from learn_to_cloud.verification.deployed_api import validate_deployed_api
from learn_to_cloud.verification.devops_verification import verify_devops_pipeline
from learn_to_cloud.verification.evidence import (
    EvidenceError,
    collect_submitted_text_evidence,
    record_evidence_decision,
    validate_evidence_bundle,
)
from learn_to_cloud.verification.github_api import GitHub, GitHubClient
from learn_to_cloud.verification.github_profile import (
    validate_profile_readme,
    validate_repo_fork,
)
from learn_to_cloud.verification.grading_requests import (
    LLMGradingRequest,
    build_repo_rubric_message,
    build_text_rubric_message,
)
from learn_to_cloud.verification.repository_ownership import (
    OwnedRepository,
    check_repository_ownership,
)
from learn_to_cloud.verification.repository_target import GitHubRepositoryTarget
from learn_to_cloud.verification.security_scanning import verify_security_scanning
from learn_to_cloud.verification.submission_values import (
    DeployedUrlValue,
    SubmittedValue,
    TextValue,
    TokenValue,
)
from learn_to_cloud.verification.tasks.phase7 import CAREER_REFLECTION_RUBRIC_TASK
from learn_to_cloud.verification.token_base import (
    verify_ctf_token,
    verify_networking_token,
)

_tracer = trace.get_tracer(__name__)

_USERNAME_OPTIONAL = frozenset(
    {SubmissionType.DEPLOYED_API, SubmissionType.CAREER_REFLECTION}
)


def _grading_request(
    job: PreparedVerificationAttempt,
    target: GitHubRepositoryTarget | None,
    deterministic_result: ValidationResult,
    grading: GradingEvidence,
) -> LLMGradingRequest:
    """Build the recorded grading request from a passing check's evidence.

    A task whose evidence source is ``submitted_text`` grades free text with no
    repository (Phase 7); every other task requires a repository target.
    """
    task = grading.task
    evidence = grading.bundle.model_dump(mode="json")
    allowed_evidence_refs = [
        str(item["path"])
        for item in evidence.get("items", [])
        if isinstance(item, dict) and item.get("path")
    ]
    if deterministic_result.task_results:
        allowed_evidence_refs.extend(
            task_result.task_name for task_result in deterministic_result.task_results
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
            raise ValueError(f"Repository rubric task {task.id} has no target")
        message = build_repo_rubric_message(
            requirement_slug=job.requirement.slug,
            requirement_name=job.requirement.name,
            deterministic_result=deterministic_result,
            owner=target.owner,
            repo=target.repo,
            task=task,
            evidence=evidence,
        )
    return LLMGradingRequest(
        task=task,
        message=message,
        allowed_evidence_refs=allowed_evidence_refs,
    )


def _result_state(result: ValidationResult) -> str:
    if result.is_valid:
        return "passed"
    if not result.verification_completed:
        return "unavailable"
    return "failed"


def _value[T: SubmittedValue](job: PreparedVerificationAttempt, kind: type[T]) -> T:
    value = job.submitted_value
    if not isinstance(value, kind):
        raise TypeError(f"{job.requirement.submission_type} requires {kind.__name__}")
    return value


def _owned(repository: OwnedRepository | None) -> OwnedRepository:
    if repository is None:
        raise ValueError("Repository check ran without an ownership-verified target")
    return repository


def _career_reflection(text: str) -> CheckResult:
    task = CAREER_REFLECTION_RUBRIC_TASK
    bundle = collect_submitted_text_evidence(task, text, "career-reflection.md")
    return CheckResult(
        validation_result=ValidationResult(
            is_valid=True,
            message="Reflection received. Reviewing your answers.",
        ),
        grading=GradingEvidence(task=task, bundle=bundle),
    )


async def _dispatch(
    job: PreparedVerificationAttempt,
    repository: OwnedRepository | None,
    github: GitHub,
) -> CheckResult:
    username = job.github_username or ""
    submission_type = job.requirement.submission_type
    match submission_type:
        case SubmissionType.PROFILE_README:
            _owned(repository)
            result = validate_profile_readme()
        case SubmissionType.REPO_FORK:
            result = validate_repo_fork(_owned(repository))
        case SubmissionType.CTF_TOKEN:
            result = verify_ctf_token(_value(job, TokenValue).token, username)
        case SubmissionType.NETWORKING_TOKEN:
            result = verify_networking_token(_value(job, TokenValue).token, username)
        case SubmissionType.JOURNAL_API_VERIFIER:
            target = _owned(repository).target
            result = await verify_ci_status(target.owner, target.repo, github)
        case SubmissionType.DEPLOYED_API:
            result = await validate_deployed_api(_value(job, DeployedUrlValue).url)
        case SubmissionType.DEVOPS_VERIFICATION:
            target = _owned(repository).target
            result = await verify_devops_pipeline(target.owner, target.repo, github)
        case SubmissionType.SECURITY_SCANNING:
            return await verify_security_scanning(_owned(repository).target, github)
        case SubmissionType.CAREER_REFLECTION:
            return _career_reflection(_value(job, TextValue).text)
        case _:
            assert_never(submission_type)
    return CheckResult(validation_result=result)


async def _run_check(
    job: PreparedVerificationAttempt,
    repository: OwnedRepository | None,
    github: GitHub,
) -> CheckResult:
    with _tracer.start_as_current_span(
        "verification.step",
        attributes={"verification.check.name": job.requirement.submission_type.value},
    ) as span:
        try:
            result = await _dispatch(job, repository, github)
            if result.grading is not None:
                validate_evidence_bundle(result.grading.task, result.grading.bundle)
        except EvidenceError as exc:
            if not exc.recorded:
                record_evidence_decision(exc.code)
            result = CheckResult(validation_result=exc.to_validation_result())
        result_state = _result_state(result.validation_result)
        span.set_attribute("verification.step.result", result_state)
        if result_state == "unavailable":
            span.set_status(Status(StatusCode.ERROR))
        return result


async def run_verification(
    job: PreparedVerificationAttempt,
    *,
    github: GitHub | None = None,
) -> VerificationRunResult:
    """Check repository ownership, then run the submission type's check.

    A passing check's grading evidence becomes a grading request.
    """
    if (
        job.requirement.submission_type not in _USERNAME_OPTIONAL
        and not job.github_username
    ):
        return VerificationRunResult(
            attempt=job,
            validation_result=ValidationResult(
                is_valid=False,
                message="GitHub username is required for this verification",
                username_match=False,
            ),
            grading_requests=[],
        )

    github = github or GitHubClient()
    repository: OwnedRepository | None = None
    target = job.target
    if target is not None:
        with _tracer.start_as_current_span(
            "verification.step",
            attributes={"verification.check.name": "github_repository_ownership"},
        ) as span:
            ownership = await check_repository_ownership(target, job.user_id, github)
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
                )
            span.set_attribute("verification.step.result", "passed")
            repository = ownership
            target = ownership.target

    result = await _run_check(job, repository, github)
    validation_result = result.validation_result

    grading_requests: list[LLMGradingRequest] = []
    if (
        validation_result.is_valid
        and validation_result.verification_completed
        and result.grading is not None
    ):
        try:
            grading_requests = [
                _grading_request(job, target, validation_result, result.grading)
            ]
        except EvidenceError as exc:
            record_evidence_decision(exc.code)
            validation_result = exc.to_validation_result()

    return VerificationRunResult(
        attempt=job,
        validation_result=validation_result,
        grading_requests=grading_requests,
    )
