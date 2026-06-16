"""The WorkflowRuns seam: read access to a repository's CI workflow runs.

Phase 3 grading trusts the test suite that ships with the upstream starter
repository: a green GitHub Actions run on ``main`` is the acceptance gate.
The only question asked of GitHub is "what is the most recent run of this
workflow on this branch?" This small interface captures exactly that.

Two adapters justify the seam: :class:`GitHubApiWorkflowRuns` talks to live
GitHub in production, :class:`InMemoryWorkflowRuns` answers from in-memory
data in tests. ``verify_ci_status`` accepts an optional ``WorkflowRuns`` and
falls back to :func:`default_workflow_runs` when none is supplied.
"""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable

from learn_to_cloud_shared.verification.github_http import github_api_get


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
        runs: list[dict[str, Any]] = response.json().get("workflow_runs", [])
        return runs[0] if runs else None


class InMemoryWorkflowRuns:
    """Test adapter answering from in-memory data.

    ``run`` is the run JSON returned by ``latest_run`` (``None`` models a
    repository with no runs). Set ``error`` to make ``latest_run`` raise (for
    example an ``httpx.HTTPStatusError`` for a missing workflow file).
    """

    def __init__(
        self,
        run: dict[str, Any] | None = None,
        *,
        error: Exception | None = None,
    ) -> None:
        self._run = run
        self._error = error

    async def latest_run(
        self, owner: str, repo: str, workflow: str, branch: str = "main"
    ) -> dict[str, Any] | None:
        if self._error is not None:
            raise self._error
        return self._run


_DEFAULT_WORKFLOW_RUNS = GitHubApiWorkflowRuns()


def default_workflow_runs() -> WorkflowRuns:
    """Return the shared production adapter used when no port is injected."""
    return _DEFAULT_WORKFLOW_RUNS
