"""Verify Phase 5 delivery using workflow and job outcomes only."""

from __future__ import annotations

import logging
import re
from json import JSONDecodeError

import httpx
from opentelemetry import trace
from pydantic import Field, ValidationError

from learn_to_cloud_shared.schemas import TaskResult, ValidationResult
from learn_to_cloud_shared.verification.github_errors import github_error_to_result
from learn_to_cloud_shared.verification.github_http import RETRIABLE_EXCEPTIONS
from learn_to_cloud_shared.verification.repo_ref import RepoRef, default_repo_ref
from learn_to_cloud_shared.verification.workflow_jobs import (
    WorkflowJobs,
    WorkflowJobsResponseError,
    default_workflow_jobs,
)
from learn_to_cloud_shared.verification.workflow_runs import (
    WorkflowRun,
    WorkflowRuns,
    default_workflow_runs,
)

logger = logging.getLogger(__name__)
DEVOPS_WORKFLOW_FILE = "ci.yml"
DEVOPS_REQUIRED_JOBS = ("test", "build", "deploy")
_RETRY_INSTRUCTIONS = (
    "Push your changes to main or choose Re-run all jobs for the current commit, "
    "then submit again after test, build, and deploy succeed."
)


class _DevopsRun(WorkflowRun):
    run_attempt: int = Field(gt=0)


def _invalid_metadata() -> ValidationResult:
    logger.warning(
        "devops.invalid_metadata", extra={"error.type": "response_validation"}
    )
    trace.get_current_span().add_event("devops.invalid_metadata")
    return ValidationResult(
        is_valid=False,
        verification_completed=False,
        message="Couldn't read complete GitHub delivery results. Try again later.",
    )


async def verify_devops_pipeline(
    owner: str,
    repo: str,
    runs: WorkflowRuns | None = None,
    jobs: WorkflowJobs | None = None,
    ref: RepoRef | None = None,
) -> ValidationResult:
    """Require a passing current-main run and all three successful delivery jobs."""
    runs = runs or default_workflow_runs()
    jobs = jobs or default_workflow_jobs()
    ref = ref or default_repo_ref()
    stage = "workflow"
    try:
        latest = await runs.latest_run(owner, repo, DEVOPS_WORKFLOW_FILE)
        if latest is None:
            return ValidationResult(
                is_valid=False,
                message="No ci.yml runs found on main. " + _RETRY_INSTRUCTIONS,
            )
        run = _DevopsRun.model_validate(latest, strict=True)
        run_url = f"https://github.com/{owner}/{repo}/actions/runs/{run.id}"
        if run.head_branch != "main":
            return ValidationResult(
                is_valid=False,
                message="ci.yml must run on main. " + _RETRY_INSTRUCTIONS,
            )
        if run.status != "completed":
            return ValidationResult(
                is_valid=False,
                message=f"ci.yml is still {run.status}. Wait for {run_url} to finish.",
            )
        if not run.conclusion:
            return _invalid_metadata()
        if run.conclusion != "success":
            return ValidationResult(
                is_valid=False,
                message=f"ci.yml finished with {run.conclusion}. Review {run_url}. "
                + _RETRY_INSTRUCTIONS,
            )

        stage = "jobs"
        results = await jobs.for_attempt(owner, repo, run.id, run.run_attempt)
        if any(
            job.run_id != run.id
            or job.head_sha != run.head_sha
            or job.run_attempt not in (None, run.run_attempt)
            or (job.status == "completed" and not job.conclusion)
            for job in results
        ) or len({job.id for job in results}) != len(results):
            return _invalid_metadata()

        stage = "branch"
        head_sha = await ref.head_sha(owner, repo)
        if not isinstance(head_sha, str) or not re.fullmatch(r"[0-9a-f]{40}", head_sha):
            return _invalid_metadata()
        if head_sha != run.head_sha:
            return ValidationResult(
                is_valid=False,
                message="ci.yml passed, but not on your current main commit. "
                + _RETRY_INSTRUCTIONS,
            )
    except (
        ValidationError,
        JSONDecodeError,
        UnicodeDecodeError,
        WorkflowJobsResponseError,
    ):
        return _invalid_metadata()
    except (httpx.HTTPStatusError, *RETRIABLE_EXCEPTIONS) as exc:
        if isinstance(exc, httpx.HTTPStatusError) and exc.response.status_code == 404:
            if stage == "workflow":
                return ValidationResult(
                    is_valid=False,
                    message="Commit .github/workflows/ci.yml and enable GitHub Actions "
                    "on your fork. " + _RETRY_INSTRUCTIONS,
                )
            if stage == "branch":
                return ValidationResult(
                    is_valid=False,
                    message="Your public repository needs a main branch.",
                )
            return _invalid_metadata()
        return github_error_to_result(exc, event="devops_pipeline.api_error")

    task_results: list[TaskResult] = []
    for name in DEVOPS_REQUIRED_JOBS:
        matching = [job for job in results if job.name == name]
        passed = (
            len(matching) == 1
            and matching[0].status == "completed"
            and matching[0].conclusion == "success"
        )
        if len(matching) != 1:
            feedback = (
                f"Expected one job named '{name}' in attempt {run.run_attempt}; "
                f"found {len(matching)}."
            )
        else:
            job = matching[0]
            outcome = job.conclusion if job.status == "completed" else job.status
            feedback = f"Job '{name}' finished with {outcome}."
        task_results.append(
            TaskResult(
                task_name=name,
                passed=passed,
                feedback=feedback,
                next_steps="" if passed else _RETRY_INSTRUCTIONS,
            )
        )
    passed = all(task.passed for task in task_results)
    return ValidationResult(
        is_valid=passed,
        message=(
            f"test, build, and deploy succeeded on your current main commit. {run_url}"
            if passed
            else f"ci.yml must have successful test, build, and deploy jobs. {run_url}"
        ),
        task_results=task_results,
    )
