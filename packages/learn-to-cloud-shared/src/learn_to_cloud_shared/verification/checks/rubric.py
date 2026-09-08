"""Typed rubric checks for verification workflows."""

from __future__ import annotations

import httpx
from pydantic import model_validator

from learn_to_cloud_shared.verification.core import CheckParams, StepContext, StepResult
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


class LLMRubricReviewParams(CheckParams):
    """Params for the terminal ``llm_rubric_review`` step.

    Carries the rubric ``task`` (criteria + grader). Existing workflows fetch
    exact ``evidence_paths``; workflows with dynamic filenames may discover
    files from the task's bounded ``path_patterns``.
    """

    check_name = "llm_rubric_review"
    task: VerificationTask
    evidence_paths: tuple[str, ...] = ()
    discover_paths: bool = False

    @model_validator(mode="after")
    def _validate_evidence_selection(self) -> LLMRubricReviewParams:
        if self.discover_paths == bool(self.evidence_paths):
            raise ValueError(
                "Choose exactly one LLM evidence mode: exact paths or discovery"
            )
        return self


async def _check_llm_rubric_review(
    context: StepContext,
    params: CheckParams,
) -> StepResult:
    """Fetch bounded repository evidence for a terminal LLM rubric review.

    Stops on unavailable evidence; otherwise marks the task for grading.
    The actual LLM call runs later in the separate durable
    ``run_llm_grading`` activity, so this step stays pure of any model call.
    """
    assert isinstance(params, LLMRubricReviewParams)
    target = context.repository
    if target is None:
        raise EvidenceError("evidence.configuration")
    repo_files = context.repo_files or default_repo_files()
    event = "llm_rubric_review.repo_file_error"
    try:
        if params.discover_paths:
            event = "llm_rubric_review.repo_tree_error"
            all_files = await repo_files.tree(target.owner, target.repo)
            event = "llm_rubric_review.repo_file_error"
            bundle = await collect_repo_file_evidence(
                repo_files,
                target.owner,
                target.repo,
                [],
                params.task,
                inventory=all_files,
            )
        else:
            bundle = await collect_repo_file_evidence(
                repo_files,
                target.owner,
                target.repo,
                list(params.evidence_paths),
                params.task,
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
        grading_task=params.task,
    )
