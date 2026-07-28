"""Deterministic repository checks for the Phase 5 DevOps capstone."""

from __future__ import annotations

import httpx
from opentelemetry import trace

from learn_to_cloud_shared.schemas import TaskResult, ValidationResult
from learn_to_cloud_shared.verification.errors import github_error_to_result
from learn_to_cloud_shared.verification.evidence import select_repo_paths
from learn_to_cloud_shared.verification.github_http import RETRIABLE_EXCEPTIONS
from learn_to_cloud_shared.verification.repo_files import RepoFiles, default_repo_files
from learn_to_cloud_shared.verification.tasks.phase5 import (
    PHASE5_EVIDENCE_PATH_PATTERNS,
    PHASE5_MAX_EVIDENCE_FILES,
    PHASE5_REQUIRED_PATHS,
)

_tracer = trace.get_tracer(__name__)
_FILES_TASK_NAME = "Required DevOps Files"


def missing_required_devops_paths(all_files: list[str]) -> list[str]:
    """Return required exact paths or directory prefixes absent from the tree."""
    normalized = {path.casefold() for path in all_files}
    missing: list[str] = []
    for required in PHASE5_REQUIRED_PATHS:
        normalized_required = required.casefold()
        if required.endswith("/"):
            present = any(path.startswith(normalized_required) for path in normalized)
        else:
            present = normalized_required in normalized
        if not present:
            missing.append(required)
    return missing


def select_devops_evidence_paths(
    all_files: list[str],
    *,
    max_files: int = PHASE5_MAX_EVIDENCE_FILES,
) -> list[str]:
    """Select bounded DevOps files, prioritizing prescribed exact paths."""
    return select_repo_paths(
        all_files,
        PHASE5_EVIDENCE_PATH_PATTERNS,
        max_files=max_files,
    )


def check_required_devops_files(all_files: list[str]) -> ValidationResult:
    """Build the authoritative required-files gate result."""
    missing = missing_required_devops_paths(all_files)
    if missing:
        missing_text = ", ".join(missing)
        return ValidationResult(
            is_valid=False,
            message="Required DevOps files are missing.",
            task_results=[
                TaskResult(
                    task_name=_FILES_TASK_NAME,
                    passed=False,
                    feedback=f"Missing required path(s): {missing_text}.",
                    next_steps=(
                        "Add the missing files or directories to your "
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
    with _tracer.start_as_current_span(
        "devops_required_files",
        attributes={"github.owner": owner, "github.repo": repo},
    ) as span:
        try:
            all_files = await repo_files.tree(owner, repo)
        except (httpx.HTTPStatusError, *RETRIABLE_EXCEPTIONS) as exc:
            span.record_exception(exc)
            return github_error_to_result(
                exc,
                event="devops_analysis.repo_tree_error",
                context={"owner": owner, "repo": repo},
            )

        result = check_required_devops_files(all_files)
        span.set_attribute("verification.passed", result.is_valid)
        span.set_attribute("repo.total_files", len(all_files))
        return result
