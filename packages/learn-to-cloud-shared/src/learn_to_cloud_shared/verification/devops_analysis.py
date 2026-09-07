"""Deterministic repository checks for the Phase 5 DevOps capstone."""

from __future__ import annotations

import httpx
from opentelemetry import trace

from learn_to_cloud_shared.schemas import TaskResult, ValidationResult
from learn_to_cloud_shared.verification.evidence import (
    EvidenceError,
    missing_required_evidence,
    record_evidence_decision,
    resolve_evidence_selection,
)
from learn_to_cloud_shared.verification.github_errors import github_error_to_result
from learn_to_cloud_shared.verification.github_http import RETRIABLE_EXCEPTIONS
from learn_to_cloud_shared.verification.repo_files import RepoFiles, default_repo_files
from learn_to_cloud_shared.verification.tasks.phase5 import (
    DEVOPS_IMPLEMENTATION_RUBRIC_TASK,
    PHASE5_MAX_EVIDENCE_FILES,
)

_FILES_TASK_NAME = "Required DevOps Files"


def missing_required_devops_paths(all_files: list[str]) -> list[str]:
    """Use the same typed source requirements as evidence collection."""
    return missing_required_evidence(
        all_files,
        DEVOPS_IMPLEMENTATION_RUBRIC_TASK.evidence,
    )


def select_devops_evidence_paths(
    all_files: list[str],
    *,
    max_files: int = PHASE5_MAX_EVIDENCE_FILES,
) -> list[str]:
    """Select all matching source or report the service's file limit."""
    selection = resolve_evidence_selection(all_files, DEVOPS_IMPLEMENTATION_RUBRIC_TASK)
    if len(selection.paths) > max_files:
        raise EvidenceError("evidence.file_limit")
    return selection.paths


def check_required_devops_files(all_files: list[str]) -> ValidationResult:
    """Build the authoritative required-files gate result."""
    missing = missing_required_devops_paths(all_files)
    if missing:
        record_evidence_decision("evidence.required_missing")
        missing_text = ", ".join(missing)
        return ValidationResult(
            is_valid=False,
            message="Required DevOps files are missing.",
            error_code="evidence.required_missing",
            task_results=[
                TaskResult(
                    task_name=_FILES_TASK_NAME,
                    passed=False,
                    feedback=f"Missing required path(s): {missing_text}.",
                    next_steps=(
                        "Add the missing named files or matching source files to your "
                        "journal-starter repository, then submit again."
                    ),
                )
            ],
        )

    return ValidationResult(
        is_valid=True,
        message="Required DevOps files are present.",
        task_results=[
            TaskResult(
                task_name=_FILES_TASK_NAME,
                passed=True,
                feedback=(
                    "Found the Dockerfile, GitHub Actions workflow, Terraform "
                    "configuration, and required Kubernetes manifests."
                ),
            )
        ],
    )


async def verify_required_devops_files(
    owner: str,
    repo: str,
    repo_files: RepoFiles | None = None,
) -> ValidationResult:
    """Fetch the repository tree and run the required-files gate."""
    repo_files = repo_files or default_repo_files()
    span = trace.get_current_span()
    try:
        all_files = await repo_files.tree(owner, repo)
    except EvidenceError as exc:
        record_evidence_decision(exc.code)
        return exc.to_validation_result()
    except (httpx.HTTPStatusError, *RETRIABLE_EXCEPTIONS) as exc:
        record_evidence_decision("retrieval")
        return github_error_to_result(
            exc,
            event="devops_analysis.repo_tree_error",
        )

    result = check_required_devops_files(all_files)
    span.add_event("devops.required_files_checked")
    return result
