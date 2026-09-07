"""Verify the full Journal capstone workflow on the current main commit."""

from __future__ import annotations

import logging
import re
from json import JSONDecodeError
from typing import Literal

import httpx
from opentelemetry import trace
from pydantic import Field, ValidationError

from learn_to_cloud_shared.schemas import FrozenModel, TaskResult, ValidationResult
from learn_to_cloud_shared.verification.github_errors import github_error_to_result
from learn_to_cloud_shared.verification.github_http import RETRIABLE_EXCEPTIONS
from learn_to_cloud_shared.verification.repo_ref import RepoRef, default_repo_ref
from learn_to_cloud_shared.verification.workflow_runs import (
    WorkflowRuns,
    default_workflow_runs,
)

logger = logging.getLogger(__name__)
CAPSTONE_WORKFLOW_FILE = "verify-capstone.yml"
_RUN_INSTRUCTIONS = (
    "Open Actions > Verify capstone > Run workflow, select main, "
    "and submit again after it succeeds."
)


class _CapstoneRun(FrozenModel):
    id: int = Field(gt=0)
    run_number: int = Field(gt=0)
    head_branch: str = Field(min_length=1)
    event: str = Field(min_length=1)
    head_sha: str = Field(pattern=r"^[0-9a-f]{40}$")
    status: Literal[
        "queued", "requested", "waiting", "pending", "in_progress", "completed"
    ]
    conclusion: str | None


def _invalid_metadata() -> ValidationResult:
    logger.warning(
        "capstone.invalid_metadata", extra={"error.type": "response_validation"}
    )
    trace.get_current_span().add_event("capstone.invalid_metadata")
    return ValidationResult(
        is_valid=False,
        message=(
            "Couldn't read GitHub's capstone verification response. Try again later."
        ),
        verification_completed=False,
    )


async def verify_ci_status(
    owner: str,
    repo: str,
    runs: WorkflowRuns | None = None,
    ref: RepoRef | None = None,
) -> ValidationResult:
    """Require the latest manual capstone run to pass on current main HEAD."""
    runs = runs or default_workflow_runs()
    ref = ref or default_repo_ref()
    span = trace.get_current_span()
    try:
        latest_run = await runs.latest_run(owner, repo, CAPSTONE_WORKFLOW_FILE)
        run = (
            _CapstoneRun.model_validate(latest_run, strict=True)
            if latest_run is not None
            else None
        )
    except (ValidationError, JSONDecodeError, UnicodeDecodeError):
        return _invalid_metadata()
    except (httpx.HTTPStatusError, *RETRIABLE_EXCEPTIONS) as exc:
        if isinstance(exc, httpx.HTTPStatusError) and exc.response.status_code == 404:
            span.add_event("capstone.workflow_not_found")
            return ValidationResult(
                is_valid=False,
                message=(
                    f"Verify capstone workflow not found in {owner}/{repo}. "
                    "Sync your fork with learntocloud/journal-starter to get "
                    ".github/workflows/verify-capstone.yml and enable GitHub Actions. "
                    + _RUN_INSTRUCTIONS
                ),
            )
        return github_error_to_result(exc, event="capstone.api_error")

    if run is None:
        span.add_event("capstone.no_runs")
        return ValidationResult(
            is_valid=False,
            message="No Verify capstone runs found on main. " + _RUN_INSTRUCTIONS,
        )

    run_url = f"https://github.com/{owner}/{repo}/actions/runs/{run.id}"
    if run.head_branch != "main" or run.event != "workflow_dispatch":
        span.add_event("capstone.wrong_invocation")
        return ValidationResult(
            is_valid=False,
            message="Verify capstone must be run manually on main. "
            + _RUN_INSTRUCTIONS,
        )
    if run.status != "completed":
        span.add_event("capstone.still_running")
        return ValidationResult(
            is_valid=False,
            message=(
                f"Verify capstone run #{run.run_number} is still {run.status}. "
                f"Wait for it to finish at {run_url}, then submit again."
            ),
        )
    if not run.conclusion:
        return _invalid_metadata()
    if run.conclusion != "success":
        span.add_event("capstone.failed")
        return ValidationResult(
            is_valid=False,
            message=(
                f"Verify capstone run #{run.run_number} finished with "
                f"conclusion '{run.conclusion}'. Review {run_url} "
                "and fix any failures. " + _RUN_INSTRUCTIONS
            ),
        )

    try:
        head_sha = await ref.head_sha(owner, repo)
    except (ValidationError, JSONDecodeError, UnicodeDecodeError):
        return _invalid_metadata()
    except (httpx.HTTPStatusError, *RETRIABLE_EXCEPTIONS) as exc:
        if isinstance(exc, httpx.HTTPStatusError) and exc.response.status_code == 404:
            span.add_event("capstone.branch_not_found")
            return ValidationResult(
                is_valid=False,
                message=(
                    f"Could not find the main branch of {owner}/{repo}. "
                    "Make sure the repository is public and has a main branch."
                ),
            )
        return github_error_to_result(exc, event="capstone.api_error")

    if not isinstance(head_sha, str) or not re.fullmatch(r"[0-9a-f]{40}", head_sha):
        return _invalid_metadata()
    if run.head_sha != head_sha:
        span.add_event("capstone.stale_run")
        return ValidationResult(
            is_valid=False,
            message=(
                "Verify capstone passed, but not on your current main commit. "
                "Rerun Verify capstone after every new commit. " + _RUN_INSTRUCTIONS
            ),
        )

    span.add_event("capstone.passed")
    return ValidationResult(
        is_valid=True,
        message="Verify capstone passed on your current main commit.",
        task_results=[
            TaskResult(
                task_name="Verify capstone",
                passed=True,
                feedback=(
                    f"Full capstone verification passed for main commit {head_sha}. "
                    f"Run #{run.run_number}: {run_url}"
                ),
            )
        ],
    )
