"""Prepare and apply durable LLM grading for verification jobs.

Transitional home of the self-gating grading probe for the phases that have
not yet moved to a declared engine profile. Migrated phases (Phase 3 onward)
record their grading requests on the verify result via the engine's
``llm_rubric_review`` step, so they no longer route through this probe; their
branches are removed here as they migrate, and the probe is deleted once the
last graded phase is migrated.
"""

from __future__ import annotations

from learn_to_cloud_shared.schemas import (
    HandsOnRequirement,
)
from learn_to_cloud_shared.verification.career_reflection import (
    collect_career_reflection_evidence,
)
from learn_to_cloud_shared.verification.deployment_architecture import (
    collect_deployment_architecture_evidence,
)
from learn_to_cloud_shared.verification.grading_requests import (
    LLMGradingDecisionPayload,
    LLMGradingRequest,
    build_repo_rubric_message,
    build_text_rubric_message,
)
from learn_to_cloud_shared.verification.repo_files import RepoFiles, default_repo_files
from learn_to_cloud_shared.verification.security_scanning import (
    collect_security_scanning_evidence,
)
from learn_to_cloud_shared.verification.tasks import (
    PHASE4_LLM_TASKS,
    PHASE4_REQUIREMENT_SLUG,
    PHASE6_LLM_TASKS,
    PHASE7_LLM_TASKS,
    PHASE7_REQUIREMENT_SLUG,
    GradingResult,
    LLMGradingDecision,
    VerificationTask,
    require_llm_rubric_grader,
)
from learn_to_cloud_shared.verification_job_executor import (
    VerificationRunResult,
)

__all__ = [
    "LLMGradingDecisionPayload",
    "LLMGradingRequest",
    "apply_llm_grading_decisions",
    "collect_llm_grading_requests",
    "llm_grading_content_filtered_result",
    "llm_grading_unavailable_result",
]


async def collect_llm_grading_requests(
    run_result: VerificationRunResult,
    repo_files: RepoFiles | None = None,
) -> list[LLMGradingRequest]:
    """Collect evidence and prompts for tasks that require LLM grading."""
    if not run_result.validation_result.verification_completed:
        return []

    tasks = _llm_tasks_for_requirement(run_result.job.requirement)
    if not tasks:
        return []

    if run_result.job.requirement.slug == PHASE7_REQUIREMENT_SLUG:
        return _collect_phase7_requests(run_result, tasks)

    repo_files = repo_files or default_repo_files()

    if run_result.job.requirement.slug == PHASE4_REQUIREMENT_SLUG:
        return await _collect_phase4_requests(run_result, tasks, repo_files)

    if run_result.job.requirement.slug == "security-scanning":
        return await _collect_phase6_requests(run_result, tasks, repo_files)

    return []


def apply_llm_grading_decisions(
    run_result: VerificationRunResult,
    decisions: list[LLMGradingDecisionPayload],
) -> VerificationRunResult:
    """Merge LLM task decisions into the validation result."""
    if not decisions:
        return run_result

    task_results = list(run_result.validation_result.task_results or [])
    grading_results = [
        _decision_to_grading_result(payload.task, payload.decision)
        for payload in decisions
    ]
    task_results.extend(result.to_task_result() for result in grading_results)

    llm_passed = all(result.passed for result in grading_results)
    is_valid = run_result.validation_result.is_valid and llm_passed
    message = run_result.validation_result.message
    if run_result.validation_result.is_valid and not llm_passed:
        message = "LLM rubric review failed. Review the task feedback and try again."

    validation_result = run_result.validation_result.model_copy(
        update={
            "is_valid": is_valid,
            "message": message,
            "task_results": task_results,
        }
    )
    return VerificationRunResult(
        job=run_result.job,
        validation_result=validation_result,
    )


def llm_grading_unavailable_result(
    run_result: VerificationRunResult,
) -> VerificationRunResult:
    """Return a server-error validation result for LLM grader failures.

    The user-facing message stays generic; callers are responsible for
    recording the real cause in telemetry.
    """
    validation_result = run_result.validation_result.model_copy(
        update={
            "is_valid": False,
            "message": (
                "Automated grading is temporarily unavailable. This is a "
                "problem on our end, not yours. Please report it so we can "
                "fix it."
            ),
            "verification_completed": False,
        }
    )
    return VerificationRunResult(
        job=run_result.job,
        validation_result=validation_result,
    )


def llm_grading_content_filtered_result(
    run_result: VerificationRunResult,
) -> VerificationRunResult:
    """Return an actionable result when content safety blocked every retry.

    Azure's safety filter occasionally blocks a submission's free text. When
    it blocks every retry the cause is usually phrasing that looks like
    instructions or code, so the message asks the learner to rephrase and
    try again rather than blaming our systems.
    """
    validation_result = run_result.validation_result.model_copy(
        update={
            "is_valid": False,
            "message": (
                "We could not automatically review your answers because they "
                "tripped our content safety filter. This sometimes happens "
                "with certain phrasing. Please rewrite your answers in plain "
                "language, avoiding anything that reads like commands, code, "
                "or instructions, and submit again. If it keeps happening, "
                "report it so we can help."
            ),
            "verification_completed": False,
        }
    )
    return VerificationRunResult(
        job=run_result.job,
        validation_result=validation_result,
    )


async def _collect_phase6_requests(
    run_result: VerificationRunResult,
    tasks: list[VerificationTask],
    repo_files: RepoFiles,
) -> list[LLMGradingRequest]:
    target = run_result.job.target
    if target is None or not target.repo:
        return []

    owner, repo = target.owner, target.repo
    file_paths = await repo_files.tree(owner, repo)
    requests: list[LLMGradingRequest] = []
    for task in tasks:
        evidence = await collect_security_scanning_evidence(
            owner,
            repo,
            file_paths,
            task,
            repo_files=repo_files,
        )
        requests.append(
            LLMGradingRequest(
                task=task,
                message=_build_grading_message(
                    run_result=run_result,
                    task=task,
                    owner=owner,
                    repo=repo,
                    evidence=evidence.model_dump(mode="json"),
                ),
                thread_id=f"{run_result.job.id}-{task.id}",
            )
        )
    return requests


async def _collect_phase4_requests(
    run_result: VerificationRunResult,
    tasks: list[VerificationTask],
    repo_files: RepoFiles,
) -> list[LLMGradingRequest]:
    if not run_result.validation_result.is_valid:
        return []

    requirement = run_result.job.requirement
    target = run_result.job.target
    if target is None or not target.repo:
        return []

    description = run_result.job.typed_submitted_value.as_text
    deploy_script_path = getattr(
        requirement.type_config, "deploy_script_path", "deploy.sh"
    )
    requests: list[LLMGradingRequest] = []
    for task in tasks:
        evidence = await collect_deployment_architecture_evidence(
            target.owner,
            target.repo,
            description,
            task,
            deploy_script_path=deploy_script_path,
            repo_files=repo_files,
        )
        requests.append(
            LLMGradingRequest(
                task=task,
                message=_build_grading_message(
                    run_result=run_result,
                    task=task,
                    owner=target.owner,
                    repo=target.repo,
                    evidence=evidence.model_dump(mode="json"),
                ),
                thread_id=f"{run_result.job.id}-{task.id}",
            )
        )
    return requests


def _collect_phase7_requests(
    run_result: VerificationRunResult,
    tasks: list[VerificationTask],
) -> list[LLMGradingRequest]:
    if not run_result.validation_result.is_valid:
        return []

    submitted_text = run_result.job.typed_submitted_value.as_text
    requests: list[LLMGradingRequest] = []
    for task in tasks:
        evidence = collect_career_reflection_evidence(submitted_text, task)
        requests.append(
            LLMGradingRequest(
                task=task,
                message=_build_text_grading_message(
                    run_result=run_result,
                    task=task,
                    evidence=evidence.model_dump(mode="json"),
                ),
                thread_id=f"{run_result.job.id}-{task.id}",
            )
        )
    return requests


def _build_grading_message(
    *,
    run_result: VerificationRunResult,
    task: VerificationTask,
    owner: str,
    repo: str,
    evidence: dict[str, object],
) -> str:
    return build_repo_rubric_message(
        requirement_slug=run_result.job.requirement.slug,
        requirement_name=run_result.job.requirement.name,
        deterministic_result=run_result.validation_result,
        owner=owner,
        repo=repo,
        task=task,
        evidence=evidence,
    )


def _build_text_grading_message(
    *,
    run_result: VerificationRunResult,
    task: VerificationTask,
    evidence: dict[str, object],
) -> str:
    return build_text_rubric_message(
        requirement_slug=run_result.job.requirement.slug,
        requirement_name=run_result.job.requirement.name,
        deterministic_result=run_result.validation_result,
        task=task,
        evidence=evidence,
    )


def _decision_to_grading_result(
    task: VerificationTask,
    decision: LLMGradingDecision,
) -> GradingResult:
    grader = require_llm_rubric_grader(task)
    passed = decision.passed and decision.score >= grader.passing_score
    failure_reason = decision.failure_reason
    if decision.passed and not passed:
        failure_reason = "score_below_passing_threshold"

    return GradingResult(
        task_id=task.id,
        task_name=task.name,
        passed=passed,
        feedback=decision.feedback,
        next_steps=decision.next_steps,
        grader_kind=grader.kind,
        failure_reason=failure_reason,
        score=decision.score,
        confidence=decision.confidence,
        rubric_version=grader.rubric_id,
        evidence_refs=decision.evidence_refs,
    )


def _llm_tasks_for_requirement(
    requirement: HandsOnRequirement,
) -> list[VerificationTask]:
    if requirement.slug == "security-scanning":
        return PHASE6_LLM_TASKS
    if requirement.slug == PHASE7_REQUIREMENT_SLUG:
        return PHASE7_LLM_TASKS
    if requirement.slug == PHASE4_REQUIREMENT_SLUG:
        return PHASE4_LLM_TASKS
    return []
