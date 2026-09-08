"""Read complete job results for one GitHub Actions run attempt."""

from __future__ import annotations

from typing import Literal, Protocol

from pydantic import Field

from learn_to_cloud_shared.schemas import FrozenModel
from learn_to_cloud_shared.verification.github_http import github_api_get

_PAGE_SIZE = 100
_MAX_PAGES = 10


class WorkflowJobsResponseError(ValueError):
    """Job results are incomplete or inconsistent."""


class WorkflowJob(FrozenModel):
    """Job identity and outcome, without logs or step contents."""

    id: int = Field(gt=0)
    run_id: int = Field(gt=0)
    run_attempt: int | None = Field(default=None, gt=0)
    head_sha: str = Field(pattern=r"^[0-9a-f]{40}$")
    name: str = Field(min_length=1)
    status: Literal[
        "queued", "requested", "waiting", "pending", "in_progress", "completed"
    ]
    conclusion: str | None


class _JobsPage(FrozenModel):
    total_count: int = Field(ge=0)
    jobs: list[WorkflowJob]


class WorkflowJobs(Protocol):
    async def for_attempt(
        self, owner: str, repo: str, run_id: int, attempt: int
    ) -> list[WorkflowJob]: ...


class GitHubApiWorkflowJobs:
    async def for_attempt(
        self, owner: str, repo: str, run_id: int, attempt: int
    ) -> list[WorkflowJob]:
        """Fetch every page from the same attempt without following arbitrary URLs."""
        url = (
            f"https://api.github.com/repos/{owner}/{repo}/actions/runs/"
            f"{run_id}/attempts/{attempt}/jobs"
        )
        jobs: list[WorkflowJob] = []
        expected_count: int | None = None
        seen: set[int] = set()
        for page in range(1, _MAX_PAGES + 1):
            response = await github_api_get(
                url, params={"per_page": _PAGE_SIZE, "page": page}
            )
            payload = _JobsPage.model_validate(response.json(), strict=True)
            if expected_count is None:
                expected_count = payload.total_count
            if payload.total_count != expected_count:
                raise WorkflowJobsResponseError("Job count changed during pagination")
            for job in payload.jobs:
                if (
                    job.id in seen
                    or job.run_id != run_id
                    or job.run_attempt not in (None, attempt)
                ):
                    raise WorkflowJobsResponseError("Inconsistent job identity")
                seen.add(job.id)
            jobs.extend(payload.jobs)
            if len(jobs) == expected_count:
                return jobs
            if len(jobs) > expected_count or not payload.jobs:
                raise WorkflowJobsResponseError("Incomplete job listing")
        raise WorkflowJobsResponseError("Job listing exceeds the pagination limit")


_DEFAULT_WORKFLOW_JOBS = GitHubApiWorkflowJobs()


def default_workflow_jobs() -> WorkflowJobs:
    return _DEFAULT_WORKFLOW_JOBS
