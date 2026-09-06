"""The GitHubMetadata seam: existence and repository-metadata lookups.

Phase 0/1/2 hands-on grading asks two questions of GitHub that are not
about reading a repository's files: "does this URL exist?" (a HEAD request)
and "what does this repository's metadata say?" (the repo JSON, used to
confirm a fork). This small interface captures exactly those two questions.

:class:`GitHubApiMetadata` talks to live GitHub in production; tests can
inject a fake implementing the same protocol. Validators accept an optional
``GitHubMetadata`` and fall back to :class:`GitHubApiMetadata` when none
is supplied.
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
