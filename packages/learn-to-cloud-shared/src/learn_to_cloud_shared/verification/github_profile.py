"""GitHub-specific validation utilities for hands-on verification.

This module handles all GitHub-specific validations including:
- GitHub profile verification (Phase 0)
- Profile README verification (Phase 1)
- Repository fork verification (Phase 1)

For URL parsing, see ``repo_utils.parse_github_url``.
For the main hands-on verification orchestration, see hands_on_verification.py

SCALABILITY:
- Retry with exponential backoff + jitter for transient failures (3 attempts)
- Connection pooling via shared httpx.AsyncClient
"""

import httpx
from opentelemetry import trace
from tenacity import (
    RetryCallState,
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential_jitter,
)

from learn_to_cloud_shared.core.config import get_settings
from learn_to_cloud_shared.core.github_client import (
    get_github_client as _get_github_client,
)
from learn_to_cloud_shared.schemas import ValidationResult
from learn_to_cloud_shared.verification.errors import (
    GitHubServerError,
    github_error_to_result,
    make_retriable,
)
from learn_to_cloud_shared.verification.repo_utils import parse_github_url


def _parse_retry_after(header_value: str | None) -> float | None:
    """Parse Retry-After header into seconds."""
    if not header_value:
        return None
    try:
        return float(header_value)
    except ValueError:
        return None


def _wait_with_retry_after(retry_state: RetryCallState) -> float:
    """Wait respecting Retry-After header, else exponential backoff."""
    exc = retry_state.outcome.exception() if retry_state.outcome else None
    if isinstance(exc, GitHubServerError) and exc.retry_after:
        return min(exc.retry_after, 60.0)
    return wait_exponential_jitter(initial=0.5, max=10)(retry_state)


# Exceptions that should trigger retry
RETRIABLE_EXCEPTIONS: tuple[type[Exception], ...] = make_retriable(GitHubServerError)

# Re-export for backward compatibility
github_error_to_validation_result = github_error_to_result


def get_github_headers() -> dict[str, str]:
    """Get headers for GitHub API requests, including auth token if available."""
    headers = {"Accept": "application/vnd.github.v3+json"}
    settings = get_settings()
    if settings.github_token:
        headers["Authorization"] = f"Bearer {settings.github_token}"
    return headers


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
    if response.status_code >= 500:
        raise GitHubServerError(f"GitHub API returned {response.status_code}")
    if response.status_code == 429:
        retry_after = _parse_retry_after(response.headers.get("Retry-After"))
        raise GitHubServerError("GitHub rate limited (429)", retry_after=retry_after)
    response.raise_for_status()
    return response


@retry(
    stop=stop_after_attempt(3),
    wait=_wait_with_retry_after,
    retry=retry_if_exception_type(RETRIABLE_EXCEPTIONS),
    reraise=True,
)
async def _check_github_url_exists_with_retry(url: str) -> tuple[bool, str]:
    """Internal: Check URL with retry. Use check_github_url_exists() instead."""
    client = await _get_github_client()
    response = await client.head(url)

    if response.status_code >= 500:
        raise GitHubServerError(f"GitHub returned {response.status_code}")

    if response.status_code == 429:
        retry_after = _parse_retry_after(response.headers.get("Retry-After"))
        raise GitHubServerError("GitHub rate limited (429)", retry_after=retry_after)

    if response.status_code == 200:
        return True, "URL exists"
    elif response.status_code == 404:
        return False, "URL not found (404)"
    else:
        return False, f"Unexpected status code: {response.status_code}"


async def check_github_url_exists(url: str) -> ValidationResult:
    """Check if a GitHub URL exists by making a HEAD request.

    Returns:
        ValidationResult with is_valid=True if URL exists.
        verification_completed=False when the failure is infrastructure-related
        (network error, GitHub outage) so callers can
        avoid penalising the user.

    RETRY: 3 attempts with exponential backoff + jitter for transient failures.
    """
    try:
        exists, msg = await _check_github_url_exists_with_retry(url)
        return ValidationResult(is_valid=exists, message=msg)
    except RETRIABLE_EXCEPTIONS as e:
        span = trace.get_current_span()
        span.record_exception(e)
        span.add_event("url_check_failed", {"url": url})
        return ValidationResult(
            is_valid=False,
            message=f"Request error: {e!s}",
            verification_completed=False,
        )
    except Exception as e:
        span = trace.get_current_span()
        span.record_exception(e)
        span.add_event("url_check_unexpected_error", {"url": url})
        return ValidationResult(
            is_valid=False,
            message=f"Unexpected error: {e!s}",
            verification_completed=False,
        )


@retry(
    stop=stop_after_attempt(3),
    wait=_wait_with_retry_after,
    retry=retry_if_exception_type(RETRIABLE_EXCEPTIONS),
    reraise=True,
)
async def _check_repo_is_fork_of_with_retry(
    username: str, repo_name: str, original_repo: str
) -> tuple[bool, str]:
    """Internal: Check fork with retry. Use check_repo_is_fork_of() instead."""
    api_url = f"https://api.github.com/repos/{username}/{repo_name}"

    client = await _get_github_client()
    response = await client.get(api_url, headers=get_github_headers())

    if response.status_code >= 500:
        raise GitHubServerError(f"GitHub API returned {response.status_code}")

    if response.status_code == 429:
        retry_after = _parse_retry_after(response.headers.get("Retry-After"))
        raise GitHubServerError("GitHub rate limited (429)", retry_after=retry_after)

    if response.status_code == 404:
        return False, f"Repository {username}/{repo_name} not found"

    if response.status_code != 200:
        return False, f"GitHub API error: {response.status_code}"

    repo_data = response.json()

    if not repo_data.get("fork", False):
        return False, "Repository is not a fork"

    parent = repo_data.get("parent", {})
    parent_full_name = parent.get("full_name", "")

    if parent_full_name.lower() == original_repo.lower():
        return True, f"Verified fork of {original_repo}"
    else:
        return (
            False,
            f"Forked from {parent_full_name}, not {original_repo}",
        )


async def check_repo_is_fork_of(
    username: str, repo_name: str, original_repo: str
) -> ValidationResult:
    """Check if a repository is a fork of the specified original repository.

    Args:
        username: The GitHub username
        repo_name: The repository name
        original_repo: The original repo in format "owner/repo"

    Returns:
        ValidationResult with is_valid=True if repo is a fork of original_repo.
        verification_completed=False when the failure is infrastructure-related.

    RETRY: 3 attempts with exponential backoff + jitter for transient failures.
    """
    try:
        is_fork, msg = await _check_repo_is_fork_of_with_retry(
            username, repo_name, original_repo
        )
        return ValidationResult(is_valid=is_fork, message=msg)
    except RETRIABLE_EXCEPTIONS as e:
        span = trace.get_current_span()
        span.record_exception(e)
        span.add_event("fork_check_failed", {"username": username, "repo": repo_name})
        return ValidationResult(
            is_valid=False,
            message=f"Request error: {e!s}",
            verification_completed=False,
        )
    except Exception as e:
        span = trace.get_current_span()
        span.record_exception(e)
        span.add_event(
            "fork_check_unexpected_error",
            {"username": username, "repo": repo_name},
        )
        return ValidationResult(
            is_valid=False,
            message=f"Unexpected error: {e!s}",
            verification_completed=False,
        )


async def validate_github_profile(
    github_url: str, expected_username: str
) -> ValidationResult:
    """Validate a GitHub profile URL submission.

    The URL should be like: https://github.com/username
    And the username should match the expected_username (case-insensitive).
    """
    parsed = parse_github_url(github_url)

    if not parsed.is_valid or not parsed.username:
        return ValidationResult(
            is_valid=False,
            message=parsed.error or "Could not extract username from URL",
            username_match=False,
            repo_exists=False,
        )

    username = parsed.username
    username_match = username.lower() == expected_username.lower()

    if not username_match:
        return ValidationResult(
            is_valid=False,
            message=(
                f"GitHub username '{username}' does not match "
                f"your account username '{expected_username}'"
            ),
            username_match=False,
            repo_exists=False,
        )

    profile_url = f"https://github.com/{username}"
    result = await check_github_url_exists(profile_url)

    if not result.is_valid:
        return result.model_copy(
            update={
                "message": f"Could not find GitHub profile. {result.message}",
                "username_match": True,
                "repo_exists": False,
            }
        )

    return ValidationResult(
        is_valid=True,
        message=f"GitHub profile verified for @{username}",
        username_match=True,
        repo_exists=True,
    )


async def validate_profile_readme(
    github_url: str, expected_username: str
) -> ValidationResult:
    """Validate a GitHub profile README submission.

    The URL should be like: https://github.com/username/username/blob/main/README.md
    And the username should match the expected_username (case-insensitive).
    """
    parsed = parse_github_url(github_url)

    if not parsed.is_valid:
        return ValidationResult(
            is_valid=False,
            message=parsed.error or "Invalid URL",
            username_match=False,
            repo_exists=False,
        )

    username_match = parsed.username.lower() == expected_username.lower()

    if not username_match:
        return ValidationResult(
            is_valid=False,
            message=(
                f"GitHub username '{parsed.username}' does not match "
                f"your account username '{expected_username}'"
            ),
            username_match=False,
            repo_exists=False,
        )

    if parsed.repo_name and parsed.repo_name.lower() != parsed.username.lower():
        return ValidationResult(
            is_valid=False,
            message=(
                f"Profile README must be in a repo named "
                f"'{parsed.username}', not '{parsed.repo_name}'"
            ),
            username_match=True,
            repo_exists=False,
        )

    result = await check_github_url_exists(github_url)

    if not result.is_valid:
        return result.model_copy(
            update={
                "message": f"Could not find your profile README. {result.message}",
                "username_match": True,
                "repo_exists": False,
            }
        )

    return ValidationResult(
        is_valid=True,
        message="Profile README validated successfully!",
        username_match=True,
        repo_exists=True,
    )


async def validate_repo_fork(
    github_url: str, expected_username: str, required_repo: str
) -> ValidationResult:
    """Validate a repository fork submission.

    The URL should be like: https://github.com/username/repo-name
    And the repo should be a fork of the required_repo.
    """
    parsed = parse_github_url(github_url)

    if not parsed.is_valid:
        return ValidationResult(
            is_valid=False,
            message=parsed.error or "Invalid URL",
            username_match=False,
            repo_exists=False,
        )

    username_match = parsed.username.lower() == expected_username.lower()

    if not username_match:
        return ValidationResult(
            is_valid=False,
            message=(
                f"GitHub username '{parsed.username}' does not match "
                f"your account username '{expected_username}'"
            ),
            username_match=False,
            repo_exists=False,
        )

    if not parsed.repo_name:
        return ValidationResult(
            is_valid=False,
            message="Could not extract repository name from URL",
            username_match=True,
            repo_exists=False,
        )

    fork_result = await check_repo_is_fork_of(
        parsed.username, parsed.repo_name, required_repo
    )

    if not fork_result.is_valid:
        return fork_result.model_copy(
            update={
                "username_match": True,
                "repo_exists": False,
            }
        )

    return ValidationResult(
        is_valid=True,
        message=f"Repository fork validated successfully! {fork_result.message}",
        username_match=True,
        repo_exists=True,
    )
