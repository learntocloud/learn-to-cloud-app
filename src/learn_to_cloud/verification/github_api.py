"""Every GitHub read verification makes, behind one interface.

Verifiers depend on the :class:`GitHub` protocol. Production uses
:class:`GitHubClient`; tests pass an in-memory fake. Methods raise
``httpx.HTTPStatusError`` and the retriable :class:`GitHubServerError`;
callers map those to results.
"""

from __future__ import annotations

from typing import Any, Literal, Protocol

import httpx
from opentelemetry import trace
from pydantic import Field, TypeAdapter

from learn_to_cloud.core.github_client import get_github_client
from learn_to_cloud.schemas.base import FrozenModel
from learn_to_cloud.verification.evidence import EvidenceError
from learn_to_cloud.verification.github_http import (
    get_github_headers,
    github_api_get,
    raise_for_server_error,
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

    async def tree(self, owner: str, repo: str, branch: str = "main") -> list[str]:
        """Return every blob path in the repository."""
        ...

    async def file(
        self, owner: str, repo: str, path: str, branch: str = "main"
    ) -> str | None:
        """Return a file's text, or ``None`` only when it does not exist."""
        ...


class GitHubClient:
    """Production :class:`GitHub` backed by the GitHub HTTP API."""

    async def repo_metadata(self, owner: str, repo: str) -> dict[str, Any] | None:
        try:
            response = await github_api_get(f"{_API}/{owner}/{repo}")
        except httpx.HTTPStatusError as e:
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

    async def tree(self, owner: str, repo: str, branch: str = "main") -> list[str]:
        response = await github_api_get(
            f"{_API}/{owner}/{repo}/git/trees/{branch}", params={"recursive": 1}
        )
        tree_data = response.json()
        if tree_data.get("truncated"):
            raise EvidenceError("evidence.selection")
        return [
            item["path"]
            for item in tree_data.get("tree", [])
            if item.get("type") == "blob"
        ]

    async def file(
        self, owner: str, repo: str, path: str, branch: str = "main"
    ) -> str | None:
        client = await get_github_client()
        response = await client.get(
            f"https://raw.githubusercontent.com/{owner}/{repo}/{branch}/{path}",
            headers=get_github_headers(),
        )
        if response.status_code == 404:
            trace.get_current_span().add_event("github.repo_file.fetch_failed")
            return None
        raise_for_server_error(response)
        response.raise_for_status()
        return response.text
