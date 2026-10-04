"""Every GitHub read verification makes, behind one interface.

Verifiers depend on the :class:`GitHub` protocol. Production uses
:class:`GitHubClient`; tests pass an in-memory fake. Methods raise
``httpx2.HTTPStatusError`` and the retriable :class:`GitHubServerError`;
callers map those to results.
"""

from __future__ import annotations

from typing import Any, Literal, Protocol

import httpx2
from pydantic import Field, TypeAdapter

from learn_to_cloud.schemas.base import FrozenModel
from learn_to_cloud.verification.github_http import (
    github_api_get,
)

_API = "https://api.github.com/repos"
_JOBS_PAGE_SIZE = 100
_JOBS_MAX_PAGES = 10

_RunStatus = Literal[
    "queued", "requested", "waiting", "pending", "in_progress", "completed"
]


class WorkflowRun(FrozenModel):
    """GitHub run metadata used by current-commit verification gates."""

    id: int = Field(gt=0)
    run_number: int = Field(gt=0)
    head_branch: str = Field(min_length=1)
    event: str = Field(min_length=1)
    head_sha: str = Field(pattern=r"^[0-9a-f]{40}$")
    status: _RunStatus
    conclusion: str | None


class WorkflowJob(FrozenModel):
    """Job identity and outcome, without logs or step contents."""

    id: int = Field(gt=0)
    run_id: int = Field(gt=0)
    run_attempt: int | None = Field(default=None, gt=0)
    head_sha: str = Field(pattern=r"^[0-9a-f]{40}$")
    name: str = Field(min_length=1)
    status: _RunStatus
    conclusion: str | None


class GitHubApp(FrozenModel):
    slug: str = Field(min_length=1)


class Deployment(FrozenModel):
    """Deployment identity and the app that created it."""

    id: int = Field(gt=0)
    sha: str = Field(pattern=r"^[0-9a-f]{40}$")
    environment: str = Field(min_length=1)
    performed_via_github_app: GitHubApp | None


class DeploymentStatus(FrozenModel):
    state: str = Field(min_length=1)
    environment_url: str
    log_url: str


class WorkflowJobsResponseError(ValueError):
    """Job results are incomplete or inconsistent."""


class _WorkflowRunsPage(FrozenModel):
    workflow_runs: list[dict[str, Any]]


class _JobsPage(FrozenModel):
    total_count: int = Field(ge=0)
    jobs: list[WorkflowJob]


class GitHub(Protocol):
    async def repo_metadata(self, owner: str, repo: str) -> dict[str, Any] | None:
        """Return the repository JSON, or ``None`` when it does not exist."""
        ...

    async def head_sha(
        self, owner: str, repo: str, branch: str = "main"
    ) -> str | None: ...

    async def latest_run(
        self, owner: str, repo: str, workflow: str, branch: str = "main"
    ) -> dict[str, Any] | None:
        """Return the newest run of ``workflow`` on ``branch``, if any."""
        ...

    async def jobs_for_attempt(
        self, owner: str, repo: str, run_id: int, attempt: int
    ) -> list[WorkflowJob]: ...

    async def latest_deployment(
        self, owner: str, repo: str, sha: str, environment: str
    ) -> Deployment | None:
        """Return the newest deployment of ``sha`` to ``environment``, if any."""
        ...

    async def latest_deployment_status(
        self, owner: str, repo: str, deployment_id: int
    ) -> DeploymentStatus | None: ...


class GitHubClient:
    """Production :class:`GitHub` backed by the GitHub HTTP API."""

    async def repo_metadata(self, owner: str, repo: str) -> dict[str, Any] | None:
        try:
            response = await github_api_get(f"{_API}/{owner}/{repo}")
        except httpx2.HTTPStatusError as e:
            if e.response.status_code == 404:
                return None
            raise
        return response.json()

    async def head_sha(self, owner: str, repo: str, branch: str = "main") -> str | None:
        response = await github_api_get(f"{_API}/{owner}/{repo}/branches/{branch}")
        data = TypeAdapter(dict[str, Any]).validate_python(response.json(), strict=True)
        commit = data.get("commit")
        if isinstance(commit, dict):
            sha = commit.get("sha")
            if isinstance(sha, str):
                return sha
        return None

    async def latest_run(
        self, owner: str, repo: str, workflow: str, branch: str = "main"
    ) -> dict[str, Any] | None:
        response = await github_api_get(
            f"{_API}/{owner}/{repo}/actions/workflows/{workflow}/runs",
            params={"branch": branch, "per_page": 1},
        )
        runs = _WorkflowRunsPage.model_validate(
            response.json(), strict=True
        ).workflow_runs
        return runs[0] if runs else None

    async def jobs_for_attempt(
        self, owner: str, repo: str, run_id: int, attempt: int
    ) -> list[WorkflowJob]:
        """Fetch every page from the same attempt without following arbitrary URLs."""
        url = f"{_API}/{owner}/{repo}/actions/runs/{run_id}/attempts/{attempt}/jobs"
        jobs: list[WorkflowJob] = []
        expected_count: int | None = None
        seen: set[int] = set()
        for page in range(1, _JOBS_MAX_PAGES + 1):
            response = await github_api_get(
                url, params={"per_page": _JOBS_PAGE_SIZE, "page": page}
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

    async def latest_deployment(
        self, owner: str, repo: str, sha: str, environment: str
    ) -> Deployment | None:
        response = await github_api_get(
            f"{_API}/{owner}/{repo}/deployments",
            params={"sha": sha, "environment": environment, "per_page": 1},
        )
        deployments = TypeAdapter(list[Deployment]).validate_python(
            response.json(), strict=True
        )
        return deployments[0] if deployments else None

    async def latest_deployment_status(
        self, owner: str, repo: str, deployment_id: int
    ) -> DeploymentStatus | None:
        response = await github_api_get(
            f"{_API}/{owner}/{repo}/deployments/{deployment_id}/statuses",
            params={"per_page": 1},
        )
        statuses = TypeAdapter(list[DeploymentStatus]).validate_python(
            response.json(), strict=True
        )
        return statuses[0] if statuses else None
