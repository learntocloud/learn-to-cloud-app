"""The RepoRef seam: read a repository branch's current HEAD commit sha.

The Phase 6 CodeQL gate anchors to the *current* tip of ``main``: it only
passes when the latest CodeQL run's ``head_sha`` matches the branch HEAD. That
requires one small question of GitHub: "what commit is at the tip of this
branch right now?" This interface captures exactly that.

:class:`GitHubApiRepoRef` talks to live GitHub in production; tests can inject
an in-memory implementation of the same protocol.
``verify_codeql_status`` accepts an optional ``RepoRef`` and falls back to
:func:`default_repo_ref` when none is supplied.
"""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable

from learn_to_cloud_shared.verification.github_http import github_api_get


@runtime_checkable
class RepoRef(Protocol):
    """Read access to a repository branch's HEAD commit sha.

    ``head_sha`` returns the branch tip's commit sha, or ``None`` when the
    branch payload carries no sha. It raises ``httpx.HTTPStatusError`` (for
    example a 404 when the repository or branch is missing) and the retriable
    :class:`GitHubServerError`; callers already handle these.
    """

    async def head_sha(
        self, owner: str, repo: str, branch: str = "main"
    ) -> str | None: ...


class GitHubApiRepoRef:
    """Production adapter backed by the GitHub HTTP API."""

    async def head_sha(self, owner: str, repo: str, branch: str = "main") -> str | None:
        """Return the branch HEAD commit sha, or ``None`` when absent."""
        url = f"https://api.github.com/repos/{owner}/{repo}/branches/{branch}"
        response = await github_api_get(url)
        data: dict[str, Any] = response.json()
        commit = data.get("commit")
        if isinstance(commit, dict):
            sha = commit.get("sha")
            if isinstance(sha, str):
                return sha
        return None


_DEFAULT_REPO_REF = GitHubApiRepoRef()


def default_repo_ref() -> RepoRef:
    """Return the shared production adapter used when no port is injected."""
    return _DEFAULT_REPO_REF
