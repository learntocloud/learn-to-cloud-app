"""The GitHubMetadata seam: existence and repository-metadata lookups.

Phase 0/1/2 hands-on grading asks two questions of GitHub that are not
about reading a repository's files: "does this URL exist?" (a HEAD request)
and "what does this repository's metadata say?" (the repo JSON, used to
confirm a fork). This small interface captures exactly those two questions.

Two adapters justify the seam: :class:`GitHubApiMetadata` talks to live
GitHub in production, :class:`InMemoryGitHubMetadata` answers from an
in-memory mapping in tests. Validators accept an optional ``GitHubMetadata``
and fall back to :func:`default_github_metadata` when none is supplied.
"""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable

import httpx

from learn_to_cloud_shared.verification.github_http import (
    github_api_get,
    github_head_status,
)


@runtime_checkable
class GitHubMetadata(Protocol):
    """Existence and metadata lookups against GitHub.

    ``url_exists`` returns ``True`` for a 200 and ``False`` otherwise (for
    example a 404). ``repo_metadata`` returns the repository JSON, or
    ``None`` when the repository does not exist (404). Both raise the
    retriable :class:`GitHubServerError` on 5xx/429 and propagate
    ``httpx`` network errors; callers map those to an incomplete result.
    """

    async def url_exists(self, url: str) -> bool: ...

    async def repo_metadata(self, owner: str, repo: str) -> dict[str, Any] | None: ...


class GitHubApiMetadata:
    """Production adapter backed by the GitHub HTTP API."""

    async def url_exists(self, url: str) -> bool:
        """Return ``True`` when a HEAD request to ``url`` returns 200."""
        status = await github_head_status(url)
        return status == 200

    async def repo_metadata(self, owner: str, repo: str) -> dict[str, Any] | None:
        """Return the repository JSON, or ``None`` when it does not exist."""
        url = f"https://api.github.com/repos/{owner}/{repo}"
        try:
            response = await github_api_get(url)
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                return None
            raise
        return response.json()


class InMemoryGitHubMetadata:
    """Test adapter answering from in-memory data.

    ``existing_urls`` is the set of URLs that should report as existing.
    ``repos`` maps ``"owner/repo"`` to its metadata JSON; a missing key
    reports as a 404 (``None``). Set ``url_error`` or ``repo_error`` to make
    the matching call raise (for example a ``GitHubServerError`` or an
    ``httpx`` network error) to model infrastructure failures.
    """

    def __init__(
        self,
        *,
        existing_urls: set[str] | None = None,
        repos: dict[str, dict[str, Any]] | None = None,
        url_error: Exception | None = None,
        repo_error: Exception | None = None,
    ) -> None:
        self._existing_urls = set(existing_urls or set())
        self._repos = dict(repos or {})
        self._url_error = url_error
        self._repo_error = repo_error

    async def url_exists(self, url: str) -> bool:
        if self._url_error is not None:
            raise self._url_error
        return url in self._existing_urls

    async def repo_metadata(self, owner: str, repo: str) -> dict[str, Any] | None:
        if self._repo_error is not None:
            raise self._repo_error
        return self._repos.get(f"{owner}/{repo}")


_DEFAULT_GITHUB_METADATA = GitHubApiMetadata()


def default_github_metadata() -> GitHubMetadata:
    """Return the shared production adapter used when no port is injected."""
    return _DEFAULT_GITHUB_METADATA
