"""Configurable repository evidence check for engine contract tests."""

from __future__ import annotations

import httpx

from learn_to_cloud_shared.verification.core import StepContext, StepResult
from learn_to_cloud_shared.verification.evidence import (
    EvidenceError,
    collect_repo_file_evidence,
    record_evidence_decision,
)
from learn_to_cloud_shared.verification.github_errors import (
    GitHubServerError,
    github_error_to_result,
)
from learn_to_cloud_shared.verification.repo_files import default_repo_files
from learn_to_cloud_shared.verification.tasks.base import VerificationTask


async def check_llm_rubric_review(
    context: StepContext,
    *,
    task: VerificationTask,
    evidence_paths: tuple[str, ...] = (),
    discover_paths: bool = False,
) -> StepResult:
    """Fetch bounded repository evidence for a terminal LLM rubric review.

    Stops on unavailable evidence; otherwise marks the task for grading.
    The actual LLM call runs later in the separate durable
    ``run_llm_grading`` activity, so this step stays pure of any model call.
    """
    if discover_paths == bool(evidence_paths):
        raise ValueError(
            "Choose exactly one LLM evidence mode: exact paths or discovery"
        )
    target = context.repository
    if target is None:
        raise EvidenceError("evidence.configuration")
    repo_files = context.repo_files or default_repo_files()
    event = "llm_rubric_review.repo_file_error"
    try:
        if discover_paths:
            event = "llm_rubric_review.repo_tree_error"
            all_files = await repo_files.tree(target.owner, target.repo)
            event = "llm_rubric_review.repo_file_error"
            bundle = await collect_repo_file_evidence(
                repo_files,
                target.owner,
                target.repo,
                [],
                task,
                inventory=all_files,
            )
        else:
            bundle = await collect_repo_file_evidence(
                repo_files,
                target.owner,
                target.repo,
                list(evidence_paths),
                task,
            )
    except (GitHubServerError, httpx.HTTPStatusError, httpx.RequestError) as exc:
        if event == "llm_rubric_review.repo_tree_error":
            record_evidence_decision("retrieval")
        return StepResult(
            passed=False,
            stop_on_fail=True,
            validation_result=github_error_to_result(exc, event=event),
        )
    return StepResult(
        passed=True,
        stop_on_fail=False,
        evidence=[bundle],
        grading_task=task,
    )
