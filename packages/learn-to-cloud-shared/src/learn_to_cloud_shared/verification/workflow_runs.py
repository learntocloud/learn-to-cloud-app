"""The WorkflowRuns seam: read access to a repository's CI workflow runs.

Phase 3 trusts the full capstone workflow supplied by the upstream starter,
not ordinary CI. Callers decide which workflow and commit satisfy their gate.
The only question asked of GitHub is "what is the most recent run of this
workflow on this branch?" This small interface captures exactly that.

:class:`GitHubApiWorkflowRuns` talks to live GitHub in production; tests can
inject an in-memory implementation. ``verify_ci_status`` accepts an optional
``WorkflowRuns`` and falls back to :func:`default_workflow_runs` when none is supplied.
"""

from __future__ import annotations

from typing import Any, Literal, Protocol, runtime_checkable

from pydantic import Field

from learn_to_cloud_shared.schemas import FrozenModel
from learn_to_cloud_shared.verification.github_http import github_api_get


class WorkflowRun(FrozenModel):
    """GitHub run metadata used by current-commit verification gates."""

    id: int = Field(gt=0)
    run_number: int = Field(gt=0)
    head_branch: str = Field(min_length=1)
    event: str = Field(min_length=1)
    head_sha: str = Field(pattern=r"^[0-9a-f]{40}$")
    status: Literal[
        "queued", "requested", "waiting", "pending", "in_progress", "completed"
    ]
    conclusion: str | None


@runtime_checkable
class WorkflowRuns(Protocol):
    """Read access to a repository's GitHub Actions workflow runs.

    ``latest_run`` returns the most recent run for ``workflow`` on
    ``branch`` as the GitHub run JSON, or ``None`` when no runs exist. It
    raises ``httpx.HTTPStatusError`` (for example a 404 when the workflow
    file is absent) and the retriable :class:`GitHubServerError`; callers
    already handle these.
    """

    async def latest_run(
        self, owner: str, repo: str, workflow: str, branch: str = "main"
    ) -> dict[str, Any] | None: ...


class _WorkflowRunsResponse(FrozenModel):
    workflow_runs: list[dict[str, Any]]


class GitHubApiWorkflowRuns:
    """Production adapter backed by the GitHub HTTP API."""

    async def latest_run(
        self, owner: str, repo: str, workflow: str, branch: str = "main"
    ) -> dict[str, Any] | None:
        """Return the most recent workflow run, or ``None`` when there are none."""
        url = (
            f"https://api.github.com/repos/{owner}/{repo}"
            f"/actions/workflows/{workflow}/runs"
        )
        params: dict[str, str | int] = {"branch": branch, "per_page": 1}
        response = await github_api_get(url, params=params)
        runs = _WorkflowRunsResponse.model_validate(
            response.json(), strict=True
        ).workflow_runs
        return runs[0] if runs else None


_DEFAULT_WORKFLOW_RUNS = GitHubApiWorkflowRuns()


def default_workflow_runs() -> WorkflowRuns:
    """Return the shared production adapter used when no port is injected."""
    return _DEFAULT_WORKFLOW_RUNS
