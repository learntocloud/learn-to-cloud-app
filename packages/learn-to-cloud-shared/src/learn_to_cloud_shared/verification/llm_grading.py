"""Prepare and apply durable LLM grading for verification jobs."""

from __future__ import annotations

import json

from learn_to_cloud_shared.schemas import (
    FrozenModel,
    HandsOnRequirement,
    ValidationResult,
)
from learn_to_cloud_shared.verification.devops_analysis import fetch_repo_tree
from learn_to_cloud_shared.verification.journal_api import (
    collect_journal_api_implementation_evidence,
)
from learn_to_cloud_shared.verification.repo_utils import validate_repo_url
from learn_to_cloud_shared.verification.security_scanning import (
    collect_security_scanning_evidence,
)
from learn_to_cloud_shared.verification.tasks import (
    PHASE3_LLM_TASKS,
    PHASE6_LLM_TASKS,
    GradingResult,
    LLMGradingDecision,
    VerificationTask,
    require_llm_rubric_grader,
)
from learn_to_cloud_shared.verification.url_derivation import (
    fork_name_from_required_repo,
)
from learn_to_cloud_shared.verification_job_executor import (
    VerificationRunResult,
)


class LLMGradingRequest(FrozenModel):
    """One durable agent grading request."""

    task: VerificationTask
    message: str
    thread_id: str


class LLMGradingDecisionPayload(FrozenModel):
    """A structured LLM decision paired with its task definition."""

    task: VerificationTask
    decision: LLMGradingDecision


async def collect_llm_grading_requests(
    run_result: VerificationRunResult,
) -> list[LLMGradingRequest]:
    """Collect evidence and prompts for tasks that require LLM grading."""
    if not run_result.validation_result.verification_completed:
        return []

    tasks = _llm_tasks_for_requirement(run_result.job.requirement)
    if not tasks:
        return []

    if run_result.job.requirement.id == "security-scanning":
        return await _collect_phase6_requests(run_result, tasks)

    if run_result.job.requirement.id == "journal-api-implementation":
        return await _collect_phase3_requests(run_result, tasks)

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
    detail: str,
) -> VerificationRunResult:
    """Return a server-error validation result for LLM grader failures."""
    validation_result = run_result.validation_result.model_copy(
        update={
            "is_valid": False,
            "message": f"LLM verification grading failed: {detail}",
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
) -> list[LLMGradingRequest]:
    github_username = run_result.job.github_username
    if github_username is None:
        return []

    expected_name = _expected_fork_name(run_result.job.requirement)
    repo_result = validate_repo_url(
        run_result.job.submitted_value,
        github_username,
        expected_name,
    )
    if isinstance(repo_result, ValidationResult):
        return []

    owner, repo = repo_result
    file_paths = await fetch_repo_tree(owner, repo)
    requests: list[LLMGradingRequest] = []
    for task in tasks:
        evidence = await collect_security_scanning_evidence(
            owner,
            repo,
            file_paths,
            task,
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


async def _collect_phase3_requests(
    run_result: VerificationRunResult,
    tasks: list[VerificationTask],
) -> list[LLMGradingRequest]:
    if not run_result.validation_result.is_valid:
        return []

    github_username = run_result.job.github_username
    if github_username is None:
        return []

    expected_name = _expected_fork_name(run_result.job.requirement)
    repo_result = validate_repo_url(
        run_result.job.submitted_value,
        github_username,
        expected_name,
    )
    if isinstance(repo_result, ValidationResult):
        return []

    owner, repo = repo_result
    file_paths = await fetch_repo_tree(owner, repo)
    requests: list[LLMGradingRequest] = []
    for task in tasks:
        evidence = await collect_journal_api_implementation_evidence(
            owner,
            repo,
            file_paths,
            task,
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


def _build_grading_message(
    *,
    run_result: VerificationRunResult,
    task: VerificationTask,
    owner: str,
    repo: str,
    evidence: dict[str, object],
) -> str:
    grader = require_llm_rubric_grader(task)
    payload = {
        "requirement": {
            "id": run_result.job.requirement.id,
            "name": run_result.job.requirement.name,
        },
        "task": {
            "id": task.id,
            "name": task.name,
            "criteria": task.criteria,
            "rubric_id": grader.rubric_id,
            "prompt_version": grader.prompt_version,
            "passing_score": grader.passing_score,
        },
        "repository": {"owner": owner, "name": repo},
        "deterministic_result": run_result.validation_result.model_dump(mode="json"),
        "evidence": evidence,
    }
    return (
        "Grade this Learn to Cloud verification task using only the JSON payload. "
        "Return a structured grading decision that follows the configured schema.\n\n"
        f"{json.dumps(payload, sort_keys=True)}"
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
    if requirement.id == "security-scanning":
        return PHASE6_LLM_TASKS
    if requirement.id == "journal-api-implementation":
        return PHASE3_LLM_TASKS
    return []


def _expected_fork_name(requirement: HandsOnRequirement) -> str | None:
    if not requirement.required_repo:
        return None
    try:
        return fork_name_from_required_repo(requirement.required_repo)
    except ValueError:
        return None
