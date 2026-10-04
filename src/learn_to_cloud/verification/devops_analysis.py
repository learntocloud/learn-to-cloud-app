"""Verify Phase 5 delivery from run results, deployment records, and the live app."""

from __future__ import annotations

import logging
import re
from json import JSONDecodeError

import httpx2
from opentelemetry import trace
from pydantic import Field, ValidationError

from learn_to_cloud.schemas.verification import TaskResult, ValidationResult
from learn_to_cloud.verification.deployed_api import verify_deployed_version
from learn_to_cloud.verification.github_api import (
    GitHub,
    WorkflowJob,
    WorkflowJobsResponseError,
    WorkflowRun,
)
from learn_to_cloud.verification.github_errors import github_error_to_result
from learn_to_cloud.verification.github_http import RETRIABLE_EXCEPTIONS

logger = logging.getLogger(__name__)
DEVOPS_WORKFLOW_FILE = "ci.yml"
DEVOPS_REQUIRED_JOBS = ("test", "build", "deploy")
DEVOPS_ENVIRONMENT = "production"
DEVOPS_VERSION_PATH = "/version"
_ACTIONS_APP_SLUG = "github-actions"
_RETRY_INSTRUCTIONS = (
    "Push your changes to main or choose Re-run all jobs for the current commit, "
    "then submit again after test, build, and deploy succeed."
)
_ENVIRONMENT_INSTRUCTIONS = (
    "Give the deploy job `environment: {name: production, url: <your HTTPS API "
    "URL>}`, then choose Re-run all jobs."
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


def _job_tasks(results: list[WorkflowJob], attempt: int) -> list[TaskResult]:
    tasks: list[TaskResult] = []
    for name in DEVOPS_REQUIRED_JOBS:
        matching = [job for job in results if job.name == name]
        passed = (
            len(matching) == 1
            and matching[0].status == "completed"
            and matching[0].conclusion == "success"
        )
        if len(matching) != 1:
            feedback = (
                f"Expected one job named '{name}' in attempt {attempt}; "
                f"found {len(matching)}."
            )
        else:
            job = matching[0]
            outcome = job.conclusion if job.status == "completed" else job.status
            feedback = f"Job '{name}' finished with {outcome}."
        tasks.append(
            TaskResult(
                task_name=name,
                passed=passed,
                feedback=feedback,
                next_steps="" if passed else _RETRY_INSTRUCTIONS,
            )
        )
    return tasks


def _deployment_failure(feedback: str) -> TaskResult:
    return TaskResult(
        task_name="deployment",
        passed=False,
        feedback=feedback,
        next_steps=_ENVIRONMENT_INSTRUCTIONS,
    )


async def _deployment_task(
    owner: str,
    repo: str,
    run: _DevopsRun,
    deploy_job: WorkflowJob,
    github: GitHub,
) -> TaskResult | str | None:
    """Return the deployment URL, a learner-facing failure, or None if malformed."""
    deployment = await github.latest_deployment(
        owner, repo, run.head_sha, DEVOPS_ENVIRONMENT
    )
    if deployment is None:
        return _deployment_failure(
            "No production deployment was recorded for your current main commit."
        )
    if deployment.sha != run.head_sha:
        return None
    app = deployment.performed_via_github_app
    if app is None or app.slug != _ACTIONS_APP_SLUG:
        return _deployment_failure(
            "The production deployment must come from the deploy job's "
            "`environment`, not a separate API call."
        )
    status = await github.latest_deployment_status(owner, repo, deployment.id)
    if status is None:
        return _deployment_failure("The production deployment has no status yet.")
    expected_log = (
        f"https://github.com/{owner}/{repo}/actions/runs/{run.id}/job/{deploy_job.id}"
    )
    if status.log_url.casefold() != expected_log.casefold():
        return _deployment_failure(
            "The latest production deployment was not made by the deploy job "
            "in this run."
        )
    if status.state != "success":
        return _deployment_failure(f"The production deployment is {status.state}.")
    if not status.environment_url:
        return _deployment_failure(
            "The production environment has no URL. Set `url:` on the deploy "
            "job's environment."
        )
    return status.environment_url


async def verify_devops_pipeline(
    owner: str,
    repo: str,
    github: GitHub,
) -> ValidationResult:
    """Require current-main jobs, their production deployment, and the live commit."""
    stage = "workflow"
    try:
        latest = await github.latest_run(owner, repo, DEVOPS_WORKFLOW_FILE)
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
        results = await github.jobs_for_attempt(owner, repo, run.id, run.run_attempt)
        if any(
            job.run_id != run.id
            or job.head_sha != run.head_sha
            or job.run_attempt not in (None, run.run_attempt)
            or (job.status == "completed" and not job.conclusion)
            for job in results
        ) or len({job.id for job in results}) != len(results):
            return _invalid_metadata()

        stage = "branch"
        head_sha = await github.head_sha(owner, repo)
        if not isinstance(head_sha, str) or not re.fullmatch(r"[0-9a-f]{40}", head_sha):
            return _invalid_metadata()
        if head_sha != run.head_sha:
            return ValidationResult(
                is_valid=False,
                message="ci.yml passed, but not on your current main commit. "
                + _RETRY_INSTRUCTIONS,
            )

        task_results = _job_tasks(results, run.run_attempt)
        if not all(task.passed for task in task_results):
            return ValidationResult(
                is_valid=False,
                message="ci.yml must have successful test, build, and deploy jobs. "
                + run_url,
                task_results=task_results,
            )

        stage = "deployment"
        deploy_job = next(job for job in results if job.name == "deploy")
        deployment = await _deployment_task(owner, repo, run, deploy_job, github)
    except (
        ValidationError,
        JSONDecodeError,
        UnicodeDecodeError,
        WorkflowJobsResponseError,
    ):
        return _invalid_metadata()
    except (httpx2.HTTPStatusError, *RETRIABLE_EXCEPTIONS) as exc:
        if isinstance(exc, httpx2.HTTPStatusError) and exc.response.status_code == 404:
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

    if deployment is None:
        return _invalid_metadata()
    if isinstance(deployment, TaskResult):
        return ValidationResult(
            is_valid=False,
            message="test, build, and deploy succeeded, but the production "
            f"deployment couldn't be confirmed. {run_url}",
            task_results=[*task_results, deployment],
        )
    task_results.append(
        TaskResult(
            task_name="deployment",
            passed=True,
            feedback=f"The deploy job recorded a production deployment to "
            f"{deployment}.",
        )
    )

    live = await verify_deployed_version(deployment, run.head_sha)
    task_results.append(
        TaskResult(
            task_name="version",
            passed=live.is_valid,
            feedback=live.message,
            next_steps=""
            if live.is_valid
            else f"Serve GET {DEVOPS_VERSION_PATH} from your production URL "
            'as {"commit": "<full commit SHA>"} and keep it running until '
            "verification passes.",
        )
    )
    if not live.is_valid:
        return ValidationResult(
            is_valid=False,
            verification_completed=live.verification_completed,
            message="Your production URL isn't serving your current main commit. "
            + run_url,
            task_results=task_results,
        )
    return ValidationResult(
        is_valid=True,
        message="test, build, and deploy succeeded, and production is serving "
        f"your current main commit. {run_url}",
        task_results=task_results,
    )
