"""The RepoFiles seam: read access to a learner's GitHub repository.

Grading rules depend on this small interface (read the file tree, read a
single file's text) instead of reaching the network directly. Production
injects :class:`GitHubRepoFiles`; tests inject :class:`InMemoryRepoFiles`.

Two adapters justify the seam: live GitHub in production, an in-memory
mapping in tests. Graders accept an optional ``RepoFiles`` and fall back to
:func:`default_repo_files` when none is supplied, so callers that do not
care about the seam keep working while tests can swap in a fake.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from opentelemetry import trace

from learn_to_cloud_shared.core.github_client import get_github_client
from learn_to_cloud_shared.verification.github_http import (
    get_github_headers,
    github_api_get,
    raise_for_server_error,
)


@runtime_checkable
class RepoFiles(Protocol):
    """Read access to a GitHub repository's files.

    ``tree`` raises ``httpx.HTTPStatusError`` (for example a 404 when the
    repository is missing or private) and the retriable GitHub server
    errors raised by the production adapter; callers already handle these.
    ``file`` returns ``None`` only for a 404; other HTTP and request failures
    propagate rather than producing incomplete evidence.
    """

    async def tree(self, owner: str, repo: str, branch: str = "main") -> list[str]: ...

    async def file(
        self, owner: str, repo: str, path: str, branch: str = "main"
    ) -> str | None: ...


class GitHubRepoFiles:
    """Production adapter backed by the GitHub HTTP API."""

    async def tree(self, owner: str, repo: str, branch: str = "main") -> list[str]:
        """Return every blob path in the repository via the Git Trees API."""
        url = f"https://api.github.com/repos/{owner}/{repo}/git/trees/{branch}"
        response = await github_api_get(url, params={"recursive": 1})
        tree_data = response.json()
        return [
            item["path"]
            for item in tree_data.get("tree", [])
            if item.get("type") == "blob"
        ]

    async def file(
        self, owner: str, repo: str, path: str, branch: str = "main"
    ) -> str | None:
        """Read a raw file once, returning ``None`` only for a 404."""
        client = await get_github_client()
        headers = get_github_headers()
        url = f"https://raw.githubusercontent.com/{owner}/{repo}/{branch}/{path}"
        response = await client.get(url, headers=headers)
        if response.status_code == 404:
            span = trace.get_current_span()
            span.add_event("github.repo_file.fetch_failed")
            return None
        raise_for_server_error(response)
        response.raise_for_status()
        return response.text


class InMemoryRepoFiles:
    """Test adapter backed by an in-memory mapping of path to content.

    ``files`` maps a repository path to its text. ``tree`` defaults to the
    keys of ``files`` but can be set explicitly to model files that exist in
    the tree yet cannot be fetched. Set ``tree_error`` to make ``tree`` raise
    (for example an ``httpx.HTTPStatusError`` for a missing repository).
    """

    def __init__(
        self,
        files: dict[str, str] | None = None,
        *,
        tree: list[str] | None = None,
        tree_error: Exception | None = None,
    ) -> None:
        self._files = dict(files or {})
        self._tree = list(tree) if tree is not None else list(self._files)
        self._tree_error = tree_error

    async def tree(self, owner: str, repo: str, branch: str = "main") -> list[str]:
        if self._tree_error is not None:
            raise self._tree_error
        return list(self._tree)

    async def file(
        self, owner: str, repo: str, path: str, branch: str = "main"
    ) -> str | None:
        return self._files.get(path)


_DEFAULT_REPO_FILES = GitHubRepoFiles()


def default_repo_files() -> RepoFiles:
    """Return the shared production adapter used when no port is injected."""
    return _DEFAULT_REPO_FILES
