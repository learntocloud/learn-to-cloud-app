"""In-memory GitHub metadata for verification tests."""

from typing import Any


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
