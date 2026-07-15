"""Low-level GitHub HTTP plumbing shared by verification services.

This is the single home for talking to the GitHub API: the shared
``httpx.AsyncClient``, auth headers, retry policy, and the mapping of
5xx/429 responses to the retriable :class:`GitHubServerError`. Higher-level
seams (``GitHubMetadata``, ``WorkflowRuns``, ``RepoFiles``) and the profile
validators build on top of these primitives instead of each re-implementing
retry and error handling.

SCALABILITY:
- Retry with exponential backoff + jitter for transient failures (3 attempts).
- Connection pooling via the shared ``httpx.AsyncClient``.
"""

from __future__ import annotations

import httpx
from tenacity import (
    RetryCallState,
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential_jitter,
)

from learn_to_cloud_shared.core.config import get_worker_settings
from learn_to_cloud_shared.core.github_client import (
    get_github_client as _get_github_client,
)
from learn_to_cloud_shared.verification.errors import GitHubServerError, make_retriable

# Exceptions that should trigger retry.
RETRIABLE_EXCEPTIONS: tuple[type[Exception], ...] = make_retriable(GitHubServerError)


def _parse_retry_after(header_value: str | None) -> float | None:
    """Parse a ``Retry-After`` header into seconds."""
    if not header_value:
        return None
    try:
        return float(header_value)
    except ValueError:
        return None


def _wait_with_retry_after(retry_state: RetryCallState) -> float:
    """Wait respecting ``Retry-After`` when present, else exponential backoff."""
    exc = retry_state.outcome.exception() if retry_state.outcome else None
    if isinstance(exc, GitHubServerError) and exc.retry_after:
        return min(exc.retry_after, 60.0)
    return wait_exponential_jitter(initial=0.5, max=10)(retry_state)


def get_github_headers() -> dict[str, str]:
    """Get headers for GitHub API requests, including the auth token if set."""
    headers = {"Accept": "application/vnd.github.v3+json"}
    settings = get_worker_settings()
    if settings.github.token:
        headers["Authorization"] = f"Bearer {settings.github.token}"
    return headers


def raise_for_server_error(response: httpx.Response) -> None:
    """Map a 5xx or 429 response to the retriable :class:`GitHubServerError`."""
    if response.status_code >= 500:
        raise GitHubServerError(f"GitHub returned {response.status_code}")
    if response.status_code == 429:
        retry_after = _parse_retry_after(response.headers.get("Retry-After"))
        raise GitHubServerError("GitHub rate limited (429)", retry_after=retry_after)


@retry(
    stop=stop_after_attempt(3),
    wait=_wait_with_retry_after,
    retry=retry_if_exception_type(RETRIABLE_EXCEPTIONS),
    reraise=True,
)
async def github_api_get(
    url: str,
    *,
    extra_headers: dict[str, str] | None = None,
    params: dict[str, str | int] | None = None,
) -> httpx.Response:
    """Resilient GitHub API GET with retry and 5xx/429 mapping.

    Raises:
        GitHubServerError: On 5xx or 429 (triggers retry).
        httpx.HTTPStatusError: On non-retriable HTTP errors (4xx).
    """
    client = await _get_github_client()
    headers = get_github_headers()
    if extra_headers:
        headers.update(extra_headers)
    response = await client.get(url, headers=headers, params=params)
    raise_for_server_error(response)
    response.raise_for_status()
    return response


@retry(
    stop=stop_after_attempt(3),
    wait=_wait_with_retry_after,
    retry=retry_if_exception_type(RETRIABLE_EXCEPTIONS),
    reraise=True,
)
async def github_head_status(url: str) -> int:
    """Resilient GitHub HEAD returning the status code, with 5xx/429 retry.

    Raises:
        GitHubServerError: On 5xx or 429 (triggers retry).
    """
    client = await _get_github_client()
    response = await client.head(url)
    raise_for_server_error(response)
    return response.status_code
