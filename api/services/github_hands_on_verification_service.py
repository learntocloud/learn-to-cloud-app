"""GitHub-specific validation utilities for hands-on verification.

This module handles all GitHub-specific validations including:
- GitHub profile verification (Phase 0)
- Profile README verification (Phase 1)
- Repository fork verification (Phase 1)
- GitHub URL parsing

For the main hands-on verification orchestration, see hands_on_verification.py

SCALABILITY:
- Circuit breaker fails fast when GitHub API is unavailable (5 failures -> 60s)
- Retry with exponential backoff + jitter for transient failures (3 attempts)
- Connection pooling via shared httpx.AsyncClient
"""

import asyncio
import logging
import re

import httpx
from circuitbreaker import CircuitBreakerError, circuit
from tenacity import (
    RetryCallState,
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential_jitter,
)

from core.config import get_settings
from schemas import ParsedGitHubUrl, ValidationResult

logger = logging.getLogger(__name__)

# Shared HTTP client for GitHub API requests (connection pooling)
_github_http_client: httpx.AsyncClient | None = None
_github_client_lock = asyncio.Lock()


class GitHubServerError(Exception):
    """Raised when GitHub API returns a 5xx error or 429 (retriable)."""

    def __init__(self, message: str, retry_after: float | None = None):
        super().__init__(message)
        self.retry_after = retry_after


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


# Exceptions that should trigger retry and circuit breaker
RETRIABLE_EXCEPTIONS: tuple[type[Exception], ...] = (
    httpx.RequestError,
    httpx.TimeoutException,
    GitHubServerError,
)


async def _get_github_client() -> httpx.AsyncClient:
    """Get or create a shared HTTP client for GitHub API requests.

    Uses connection pooling to reduce overhead from per-request client creation.
    Thread-safe via asyncio.Lock to prevent race conditions.
    """
    global _github_http_client

    if _github_http_client is not None and not _github_http_client.is_closed:
        return _github_http_client

    async with _github_client_lock:
        # Double-check after acquiring lock
        if _github_http_client is not None and not _github_http_client.is_closed:
            return _github_http_client

        settings = get_settings()
        _github_http_client = httpx.AsyncClient(
            timeout=settings.http_timeout,
            follow_redirects=True,
            limits=httpx.Limits(max_connections=20, max_keepalive_connections=10),
        )
        return _github_http_client


async def close_github_client() -> None:
    """Close the shared GitHub HTTP client (called on application shutdown)."""
    global _github_http_client
    if _github_http_client is not None and not _github_http_client.is_closed:
        await _github_http_client.aclose()
    _github_http_client = None


def _get_github_headers() -> dict[str, str]:
    """Get headers for GitHub API requests, including auth token if available."""
    headers = {"Accept": "application/vnd.github.v3+json"}
    settings = get_settings()
    if settings.github_token:
        headers["Authorization"] = f"Bearer {settings.github_token}"
    return headers


def parse_github_url(url: str) -> ParsedGitHubUrl:
    """Parse a GitHub URL and extract components.

    Supports:
    - Profile README: https://github.com/username/username/blob/main/README.md
    - Repository: https://github.com/username/repo-name
    - Repository with path: https://github.com/username/repo-name/tree/main/folder

    Also handles common URL variations:
    - Missing https:// prefix (auto-prepends)
    - http:// prefix (converts to https://)
    - www.github.com (normalizes)
    """
    url = url.strip().rstrip("/")

    # Normalize common URL variations (always upgrade to https)
    if url.startswith("http://github.com/"):
        url = url.replace("http://", "https://")
    elif url.startswith("http://www.github.com/"):
        url = url.replace("http://www.", "https://")
    elif url.startswith("https://www.github.com/"):
        url = url.replace("https://www.", "https://")
    elif url.startswith("www.github.com/"):
        url = "https://" + url[4:]  # Remove 'www.' and add https://
    elif url.startswith("github.com/"):
        url = "https://" + url

    if not url.startswith("https://github.com/"):
        return ParsedGitHubUrl(
            username="",
            is_valid=False,
            error="URL must be a GitHub URL (e.g., https://github.com/username/repo)",
        )

    path = url.replace("https://github.com/", "")

    parts = path.split("/")

    if not parts or not parts[0]:
        return ParsedGitHubUrl(
            username="", is_valid=False, error="Could not extract username from URL"
        )

    username = parts[0]

    # GitHub usernames: 1-39 chars, alphanumeric + hyphen, can't start/end with hyphen
    if len(username) > 39 or not re.match(
        r"^[a-zA-Z0-9](?:[a-zA-Z0-9-]*[a-zA-Z0-9])?$", username
    ):
        return ParsedGitHubUrl(
            username=username, is_valid=False, error="Invalid GitHub username format"
        )

    repo_name = parts[1] if len(parts) > 1 else None

    file_path = None
    if len(parts) > 3 and parts[2] in ("blob", "tree"):
        if len(parts) > 4:
            file_path = "/".join(parts[4:])

    return ParsedGitHubUrl(
        username=username, repo_name=repo_name, file_path=file_path, is_valid=True
    )


@circuit(
    failure_threshold=5,
    recovery_timeout=60,
    expected_exception=RETRIABLE_EXCEPTIONS,
    name="github_url_circuit",
)
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

    # 5xx errors are retriable
    if response.status_code >= 500:
        raise GitHubServerError(f"GitHub returned {response.status_code}")

    # 429 rate limit is retriable
    if response.status_code == 429:
        retry_after = _parse_retry_after(response.headers.get("Retry-After"))
        raise GitHubServerError("GitHub rate limited (429)", retry_after=retry_after)

    if response.status_code == 200:
        return True, "URL exists"
    elif response.status_code == 404:
        return False, "URL not found (404)"
    else:
        return False, f"Unexpected status code: {response.status_code}"


async def check_github_url_exists(url: str) -> tuple[bool, str]:
    """Check if a GitHub URL exists by making a HEAD request.

    Returns:
        Tuple of (exists: bool, message: str)

    RETRY: 3 attempts with exponential backoff + jitter for transient failures.
    CIRCUIT BREAKER: Opens after 5 consecutive failures, recovers after 60 seconds.
    """
    try:
        return await _check_github_url_exists_with_retry(url)
    except CircuitBreakerError:
        return False, "GitHub service temporarily unavailable. Please try again later."
    except RETRIABLE_EXCEPTIONS as e:
        return False, f"Request error: {str(e)}"
    except Exception as e:
        return False, f"Unexpected error: {str(e)}"


@circuit(
    failure_threshold=5,
    recovery_timeout=60,
    expected_exception=RETRIABLE_EXCEPTIONS,
    name="github_api_circuit",
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
    response = await client.get(api_url, headers=_get_github_headers())

    # 5xx errors are retriable
    if response.status_code >= 500:
        raise GitHubServerError(f"GitHub API returned {response.status_code}")

    # 429 rate limit is retriable
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
) -> tuple[bool, str]:
    """Check if a repository is a fork of the specified original repository.

    Args:
        username: The GitHub username
        repo_name: The repository name
        original_repo: The original repo in format "owner/repo"

    RETRY: 3 attempts with exponential backoff + jitter for transient failures.
    CIRCUIT BREAKER: Opens after 5 consecutive failures, recovers after 60 seconds.
    """
    try:
        return await _check_repo_is_fork_of_with_retry(
            username, repo_name, original_repo
        )
    except CircuitBreakerError:
        return False, "GitHub service temporarily unavailable. Please try again later."
    except RETRIABLE_EXCEPTIONS as e:
        return False, f"Request error: {str(e)}"
    except Exception as e:
        return False, f"Unexpected error: {str(e)}"


async def validate_github_profile(
    github_url: str, expected_username: str
) -> ValidationResult:
    """Validate a GitHub profile URL submission.

    The URL should be like: https://github.com/username
    And the username should match the expected_username (case-insensitive).
    """
    url = github_url.strip().rstrip("/")

    if not url.startswith("https://github.com/"):
        return ValidationResult(
            is_valid=False,
            message="URL must be a GitHub profile URL (https://github.com/username)",
            username_match=False,
            repo_exists=False,
        )

    path = url.replace("https://github.com/", "")
    parts = path.split("/")
    username = parts[0] if parts else ""

    if not username:
        return ValidationResult(
            is_valid=False,
            message="Could not extract username from URL",
            username_match=False,
            repo_exists=False,
        )

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
    exists, exists_msg = await check_github_url_exists(profile_url)

    if not exists:
        return ValidationResult(
            is_valid=False,
            message=f"Could not find GitHub profile. {exists_msg}",
            username_match=True,
            repo_exists=False,
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

    exists, exists_msg = await check_github_url_exists(github_url)

    if not exists:
        return ValidationResult(
            is_valid=False,
            message=f"Could not find your profile README. {exists_msg}",
            username_match=True,
            repo_exists=False,
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

    is_fork, fork_msg = await check_repo_is_fork_of(
        parsed.username, parsed.repo_name, required_repo
    )

    if not is_fork:
        return ValidationResult(
            is_valid=False, message=fork_msg, username_match=True, repo_exists=False
        )

    return ValidationResult(
        is_valid=True,
        message=f"Repository fork validated successfully! {fork_msg}",
        username_match=True,
        repo_exists=True,
    )
