"""GitHub-specific validation utilities for hands-on verification.

This module handles all GitHub-specific validations including:
- GitHub profile verification
- Profile README verification
- Repository URL verification
- Repository fork verification
- GitHub URL parsing
- GitHub Actions workflow run verification
- Repository file existence checks

For the main hands-on verification orchestration, see hands_on_verification.py

SCALABILITY:
- Circuit breaker fails fast when GitHub API is unavailable (5 failures -> 60s)
- Retry with exponential backoff + jitter for transient failures (3 attempts)
- Connection pooling via shared httpx.AsyncClient
"""

import asyncio
import logging
import re
from dataclasses import dataclass
from datetime import UTC

import httpx
from circuitbreaker import circuit
from tenacity import (
    RetryCallState,
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential_jitter,
)

from core.config import get_settings
from core.telemetry import track_dependency

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
    """Custom wait that respects Retry-After header.

    Falls back to exponential backoff with jitter if no Retry-After.
    """
    exc = retry_state.outcome.exception() if retry_state.outcome else None
    if isinstance(exc, GitHubServerError) and exc.retry_after:
        # Cap at 60s to avoid pathological values
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


logger = logging.getLogger(__name__)


@dataclass
class ParsedGitHubUrl:
    """Parsed components of a GitHub URL."""

    username: str
    repo_name: str | None = None
    file_path: str | None = None
    is_valid: bool = True
    error: str | None = None


def parse_github_url(url: str) -> ParsedGitHubUrl:
    """
    Parse a GitHub URL and extract components.

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

    # Normalize common URL variations
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

    if not re.match(r"^[a-zA-Z0-9](?:[a-zA-Z0-9-]*[a-zA-Z0-9])?$", username):
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


@dataclass
class ValidationResult:
    """Result of validating a hands-on submission."""

    is_valid: bool
    message: str
    username_match: bool
    repo_exists: bool


@track_dependency("github_url_check", "HTTP")
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
    """
    Check if a GitHub URL exists by making a HEAD request.

    Returns:
        Tuple of (exists: bool, message: str)

    RETRY: 3 attempts with exponential backoff + jitter for transient failures.
    CIRCUIT BREAKER: Opens after 5 consecutive failures, recovers after 60 seconds.
    """
    try:
        return await _check_github_url_exists_with_retry(url)
    except RETRIABLE_EXCEPTIONS as e:
        logger.warning(f"All retries exhausted checking GitHub URL {url}: {e}")
        return False, f"Request error: {str(e)}"
    except Exception as e:
        logger.exception(f"Unexpected error checking GitHub URL {url}: {e}")
        return False, f"Unexpected error: {str(e)}"


@track_dependency("github_api_fork_check", "HTTP")
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
    """
    Check if a repository is a fork of the specified original repository.

    Args:
        username: The GitHub username
        repo_name: The repository name to check
        original_repo: The original repo in format "owner/repo"

    Returns:
        Tuple of (is_fork: bool, message: str)

    RETRY: 3 attempts with exponential backoff + jitter for transient failures.
    CIRCUIT BREAKER: Opens after 5 consecutive failures, recovers after 60 seconds.
    """
    try:
        return await _check_repo_is_fork_of_with_retry(
            username, repo_name, original_repo
        )
    except RETRIABLE_EXCEPTIONS as e:
        logger.warning(f"All retries exhausted checking fork status: {e}")
        return False, f"Request error: {str(e)}"
    except Exception as e:
        logger.exception(f"Unexpected error checking fork status: {e}")
        return False, f"Unexpected error: {str(e)}"


async def validate_github_profile(
    github_url: str, expected_username: str
) -> ValidationResult:
    """
    Validate a GitHub profile URL submission.

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


async def validate_repo_url(
    github_url: str, expected_username: str
) -> ValidationResult:
    """
    Validate a GitHub repository URL submission.

    The URL should be like: https://github.com/username/repo-name
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

    repo_url = f"https://github.com/{parsed.username}/{parsed.repo_name}"
    exists, exists_msg = await check_github_url_exists(repo_url)

    if not exists:
        return ValidationResult(
            is_valid=False,
            message=f"Could not find repository. {exists_msg}",
            username_match=True,
            repo_exists=False,
        )

    return ValidationResult(
        is_valid=True,
        message=f"Repository verified: {parsed.username}/{parsed.repo_name}",
        username_match=True,
        repo_exists=True,
    )


async def validate_profile_readme(
    github_url: str, expected_username: str
) -> ValidationResult:
    """
    Validate a GitHub profile README submission.

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
    """
    Validate a repository fork submission.

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


@track_dependency("github_api_workflow_runs", "HTTP")
@circuit(
    failure_threshold=5,
    recovery_timeout=60,
    expected_exception=RETRIABLE_EXCEPTIONS,
    name="github_workflow_circuit",
)
@retry(
    stop=stop_after_attempt(3),
    wait=_wait_with_retry_after,
    retry=retry_if_exception_type(RETRIABLE_EXCEPTIONS),
    reraise=True,
)
async def _fetch_workflow_runs_with_retry(username: str, repo_name: str) -> dict | None:
    """Internal: Fetch workflow runs with retry. Returns None on 404."""
    api_url = f"https://api.github.com/repos/{username}/{repo_name}/actions/runs"
    client = await _get_github_client()
    response = await client.get(
        api_url,
        headers=_get_github_headers(),
        params={"status": "success", "per_page": 10},
    )

    # 5xx errors are retriable
    if response.status_code >= 500:
        raise GitHubServerError(f"GitHub API returned {response.status_code}")

    # 429 rate limit is retriable
    if response.status_code == 429:
        retry_after = _parse_retry_after(response.headers.get("Retry-After"))
        raise GitHubServerError("GitHub rate limited (429)", retry_after=retry_after)

    if response.status_code == 404:
        return None  # Actions not enabled

    if response.status_code != 200:
        raise GitHubServerError(f"GitHub API error: {response.status_code}")

    return response.json()


async def validate_workflow_run(
    github_url: str, expected_username: str, min_successful_runs: int = 1
) -> ValidationResult:
    """
    Validate that a repository has successful GitHub Actions workflow runs.

    Checks the GitHub API for workflow runs that completed successfully
    within the last 30 days.

    Args:
        github_url: The repository URL
        expected_username: Expected GitHub username
        min_successful_runs: Minimum number of successful runs required (default: 1)

    Returns:
        ValidationResult with details about the workflow run status

    RETRY: 3 attempts with exponential backoff + jitter for transient failures.
    CIRCUIT BREAKER: Opens after 5 consecutive failures, recovers after 60 seconds.
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

    # Check if repo exists first
    repo_url = f"https://github.com/{parsed.username}/{parsed.repo_name}"
    exists, exists_msg = await check_github_url_exists(repo_url)

    if not exists:
        return ValidationResult(
            is_valid=False,
            message=f"Could not find repository. {exists_msg}",
            username_match=True,
            repo_exists=False,
        )

    # Check GitHub Actions workflow runs
    try:
        data = await _fetch_workflow_runs_with_retry(parsed.username, parsed.repo_name)
    except RETRIABLE_EXCEPTIONS as e:
        logger.warning(f"All retries exhausted checking workflow runs: {e}")
        return ValidationResult(
            is_valid=False,
            message="GitHub API request failed. Please try again.",
            username_match=True,
            repo_exists=True,
        )
    except Exception as e:
        logger.exception(f"Unexpected error checking workflow runs: {e}")
        return ValidationResult(
            is_valid=False,
            message=f"Unexpected error: {str(e)}",
            username_match=True,
            repo_exists=True,
        )

    if data is None:
        return ValidationResult(
            is_valid=False,
            message=(
                "GitHub Actions not found. Make sure Actions is enabled "
                "and you have at least one workflow file in .github/workflows/"
            ),
            username_match=True,
            repo_exists=True,
        )

    total_count = data.get("total_count", 0)
    runs = data.get("workflow_runs", [])

    if total_count == 0 or len(runs) == 0:
        return ValidationResult(
            is_valid=False,
            message=(
                "No successful workflow runs found. Run your CI/CD pipeline "
                "at least once and make sure it passes!"
            ),
            username_match=True,
            repo_exists=True,
        )

    # Check for recent runs (within last 30 days)
    from datetime import datetime, timedelta

    cutoff_date = datetime.now(UTC) - timedelta(days=30)
    recent_successful_runs = []

    for run in runs:
        run_date_str = run.get("created_at", "")
        if run_date_str:
            try:
                run_date = datetime.fromisoformat(run_date_str.replace("Z", "+00:00"))
                if run_date >= cutoff_date:
                    recent_successful_runs.append(run)
            except ValueError:
                continue

    if len(recent_successful_runs) < min_successful_runs:
        return ValidationResult(
            is_valid=False,
            message=(
                f"Found {len(recent_successful_runs)} successful runs in "
                f"the last 30 days, but {min_successful_runs} required. "
                "Run your pipeline again!"
            ),
            username_match=True,
            repo_exists=True,
        )

    # Get the most recent run info for the success message
    latest_run = recent_successful_runs[0]
    workflow_name = latest_run.get("name", "workflow")

    return ValidationResult(
        is_valid=True,
        message=(
            f"CI/CD verified! Found {len(recent_successful_runs)} "
            f"successful run(s) of '{workflow_name}' in the last 30 days."
        ),
        username_match=True,
        repo_exists=True,
    )


@track_dependency("github_api_file_search", "HTTP")
@circuit(
    failure_threshold=5,
    recovery_timeout=60,
    expected_exception=RETRIABLE_EXCEPTIONS,
    name="github_file_search_circuit",
)
@retry(
    stop=stop_after_attempt(3),
    wait=_wait_with_retry_after,
    retry=retry_if_exception_type(RETRIABLE_EXCEPTIONS),
    reraise=True,
)
async def _search_code_with_retry(
    search_query: str,
) -> dict | None:
    """Internal: Search GitHub code with retry. Returns None on 403 rate limit."""
    client = await _get_github_client()
    response = await client.get(
        "https://api.github.com/search/code",
        headers=_get_github_headers(),
        params={"q": search_query, "per_page": 5},
    )

    # 5xx errors are retriable
    if response.status_code >= 500:
        raise GitHubServerError(f"GitHub API returned {response.status_code}")

    # 429 rate limit is retriable
    if response.status_code == 429:
        retry_after = _parse_retry_after(response.headers.get("Retry-After"))
        raise GitHubServerError("GitHub rate limited (429)", retry_after=retry_after)

    # 403 often means secondary rate limit - signal to use fallback
    if response.status_code == 403:
        return None

    if response.status_code == 200:
        return response.json()

    return {"total_count": 0, "items": []}


async def validate_repo_has_files(
    github_url: str,
    expected_username: str,
    required_patterns: list[str],
    file_description: str,
) -> ValidationResult:
    """
    Validate that a repository contains files matching specified patterns.

    Uses GitHub's search API to look for files in the repository.

    Args:
        github_url: The repository URL
        expected_username: Expected GitHub username
        required_patterns: List of file patterns to search for
            (e.g., ["Dockerfile", "docker-compose"])
        file_description: Human-readable description of what we're looking for

    Returns:
        ValidationResult with details about the file search

    RETRY: 3 attempts with exponential backoff + jitter for transient failures.
    CIRCUIT BREAKER: Opens after 5 consecutive failures, recovers after 60 seconds.
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

    # Check if repo exists first
    repo_url = f"https://github.com/{parsed.username}/{parsed.repo_name}"
    exists, exists_msg = await check_github_url_exists(repo_url)

    if not exists:
        return ValidationResult(
            is_valid=False,
            message=f"Could not find repository. {exists_msg}",
            username_match=True,
            repo_exists=False,
        )

    # Normalize patterns (support path-based checks like infra/main.tf)
    pattern_specs = []
    for pattern in required_patterns:
        cleaned = pattern.strip().strip("/")
        is_dir = pattern.strip().endswith("/")
        if "/" in cleaned:
            path, name = cleaned.rsplit("/", 1)
            pattern_specs.append(
                {"raw": pattern, "path": path, "name": name, "is_dir": is_dir}
            )
        elif is_dir:
            pattern_specs.append(
                {"raw": pattern, "path": cleaned, "name": None, "is_dir": True}
            )
        else:
            pattern_specs.append(
                {"raw": pattern, "path": None, "name": cleaned, "is_dir": False}
            )

    def _pattern_matches_item(path: str, name: str, item_type: str, spec: dict) -> bool:
        path_lower = path.lower()
        name_lower = name.lower()
        spec_name = (spec.get("name") or "").lower()
        spec_path = (spec.get("path") or "").lower()

        if spec.get("is_dir"):
            if path_lower == spec_path:
                return True
            return path_lower.startswith(f"{spec_path}/")

        if spec_path:
            if not path_lower.startswith(f"{spec_path}/"):
                return False

        if not spec_name:
            return True

        if spec_name.startswith("."):
            return name_lower.endswith(spec_name)

        return (
            name_lower == spec_name
            or name_lower.startswith(spec_name)
            or name_lower.endswith(spec_name)
        )

    # Use GitHub's code search API to find files
    found_files = []

    try:
        for spec in pattern_specs:
            query_parts = [f"repo:{parsed.username}/{parsed.repo_name}"]
            if spec.get("path"):
                query_parts.append(f"path:{spec['path']}")

            if not (spec.get("is_dir") and not spec.get("name")):
                name = spec.get("name") or ""
                if name.startswith("."):
                    query_parts.append(f"extension:{name.lstrip('.')}")
                elif name:
                    query_parts.append(f"filename:{name}")

            # Search for files matching the pattern in the repo
            search_query = " ".join(query_parts)

            try:
                data = await _search_code_with_retry(search_query)
            except RETRIABLE_EXCEPTIONS as e:
                logger.warning(f"All retries exhausted searching for files: {e}")
                # Fall back to contents API
                return await _validate_repo_files_via_contents(
                    await _get_github_client(),
                    parsed.username,
                    parsed.repo_name,
                    required_patterns,
                    file_description,
                )

            # Handle rate limiting (403 returns None)
            if data is None:
                # Try alternative: check repo contents directly
                return await _validate_repo_files_via_contents(
                    await _get_github_client(),
                    parsed.username,
                    parsed.repo_name,
                    required_patterns,
                    file_description,
                )

            if data.get("total_count", 0) > 0:
                items = data.get("items", [])
                for item in items:
                    item_path = item.get("path", "")
                    item_name = item.get("name", "")
                    if _pattern_matches_item(
                        item_path,
                        item_name,
                        item.get("type", "file"),
                        spec,
                    ):
                        found_files.append(item_name or spec["raw"])

        if not found_files:
            return ValidationResult(
                is_valid=False,
                message=(
                    f"Could not find {file_description} in your repository. "
                    f"Make sure you have files like: {', '.join(required_patterns)}"
                ),
                username_match=True,
                repo_exists=True,
            )

        return ValidationResult(
            is_valid=True,
            message=f"Found {file_description}: {', '.join(set(found_files))}",
            username_match=True,
            repo_exists=True,
        )

    except Exception as e:
        logger.exception(f"Unexpected error searching for files: {e}")
        return ValidationResult(
            is_valid=False,
            message=f"Unexpected error: {str(e)}",
            username_match=True,
            repo_exists=True,
        )


async def _validate_repo_files_via_contents(
    client: httpx.AsyncClient,
    username: str,
    repo_name: str,
    required_patterns: list[str],
    file_description: str,
) -> ValidationResult:
    """
    Fallback validation using repo contents API when search is rate-limited.

    Checks root directory and common subdirectories for matching files.
    """
    found_files = []
    pattern_specs = []
    for pattern in required_patterns:
        cleaned = pattern.strip().strip("/")
        is_dir = pattern.strip().endswith("/")
        if "/" in cleaned:
            path, name = cleaned.rsplit("/", 1)
            pattern_specs.append(
                {"raw": pattern, "path": path, "name": name, "is_dir": is_dir}
            )
        elif is_dir:
            pattern_specs.append(
                {"raw": pattern, "path": cleaned, "name": None, "is_dir": True}
            )
        else:
            pattern_specs.append(
                {"raw": pattern, "path": None, "name": cleaned, "is_dir": False}
            )

    def _pattern_matches_item(path: str, name: str, item_type: str, spec: dict) -> bool:
        path_lower = path.lower()
        name_lower = name.lower()
        spec_name = (spec.get("name") or "").lower()
        spec_path = (spec.get("path") or "").lower()

        if spec.get("is_dir"):
            if path_lower == spec_path:
                return True
            return path_lower.startswith(f"{spec_path}/")

        if spec_path and not path_lower.startswith(f"{spec_path}/"):
            return False

        if not spec_name:
            return True

        if spec_name.startswith("."):
            return name_lower.endswith(spec_name)

        return (
            name_lower == spec_name
            or name_lower.startswith(spec_name)
            or name_lower.endswith(spec_name)
        )

    directories_to_check = [
        "",
        "infra",
        "terraform",
        "k8s",
        "kubernetes",
        "manifests",
        ".github/workflows",
    ]

    for directory in directories_to_check:
        path = f"/{directory}" if directory else ""
        api_url = f"https://api.github.com/repos/{username}/{repo_name}/contents{path}"

        try:
            response = await client.get(
                api_url,
                headers=_get_github_headers(),
            )

            if response.status_code != 200:
                continue

            contents = response.json()
            if not isinstance(contents, list):
                continue

            for item in contents:
                item_path = item.get("path", "")
                item_name = item.get("name", "")
                item_type = item.get("type", "file")
                for spec in pattern_specs:
                    if _pattern_matches_item(item_path, item_name, item_type, spec):
                        found_files.append(item_name or spec["raw"])

        except (httpx.RequestError, ValueError):
            continue

    if not found_files:
        return ValidationResult(
            is_valid=False,
            message=(
                f"Could not find {file_description} in your repository. "
                f"Make sure you have files like: {', '.join(required_patterns)}"
            ),
            username_match=True,
            repo_exists=True,
        )

    return ValidationResult(
        is_valid=True,
        message=f"Found {file_description}: {', '.join(set(found_files))}",
        username_match=True,
        repo_exists=True,
    )


@track_dependency("container_registry_api", "HTTP")
@circuit(
    failure_threshold=5,
    recovery_timeout=60,
    expected_exception=RETRIABLE_EXCEPTIONS,
    name="container_registry_circuit",
)
@retry(
    stop=stop_after_attempt(3),
    wait=_wait_with_retry_after,
    retry=retry_if_exception_type(RETRIABLE_EXCEPTIONS),
    reraise=True,
)
async def _check_container_image_with_retry(
    registry: str, image_path: str, tag: str
) -> ValidationResult:
    """Internal: Check container image with retry."""
    client = await _get_github_client()

    # Common Accept header for Docker manifest requests
    accept_header = (
        "application/vnd.docker.distribution.manifest.v2+json,"
        "application/vnd.oci.image.manifest.v1+json"
    )

    if registry == "docker.io":
        # Docker Hub API v2 - First get a token for the repository
        token_url = (
            f"https://auth.docker.io/token?"
            f"service=registry.docker.io&scope=repository:{image_path}:pull"
        )
        token_resp = await client.get(token_url)

        if token_resp.status_code >= 500:
            raise GitHubServerError(f"Docker Hub returned {token_resp.status_code}")

        if token_resp.status_code != 200:
            return ValidationResult(
                is_valid=False,
                message=(
                    f"Could not authenticate with Docker Hub for image '{image_path}'"
                ),
                username_match=True,
                repo_exists=False,
            )

        token = token_resp.json().get("token", "")

        # Check if the manifest exists
        manifest_url = f"https://registry-1.docker.io/v2/{image_path}/manifests/{tag}"
        manifest_resp = await client.get(
            manifest_url,
            headers={
                "Authorization": f"Bearer {token}",
                "Accept": accept_header,
            },
        )

        if manifest_resp.status_code >= 500:
            raise GitHubServerError(f"Docker Hub returned {manifest_resp.status_code}")

        if manifest_resp.status_code == 429:
            retry_after = _parse_retry_after(manifest_resp.headers.get("Retry-After"))
            raise GitHubServerError(
                "Docker Hub rate limited (429)", retry_after=retry_after
            )

        if manifest_resp.status_code == 200:
            return ValidationResult(
                is_valid=True,
                message=f"Found public Docker Hub image: {image_path}:{tag}",
                username_match=True,
                repo_exists=True,
            )
        elif manifest_resp.status_code == 404:
            return ValidationResult(
                is_valid=False,
                message=(
                    f"Image '{image_path}:{tag}' not found on Docker Hub. "
                    "Make sure it's pushed and public."
                ),
                username_match=True,
                repo_exists=False,
            )
        else:
            return ValidationResult(
                is_valid=False,
                message=(
                    "Could not verify image. Docker Hub returned "
                    f"status {manifest_resp.status_code}"
                ),
                username_match=True,
                repo_exists=False,
            )

    elif registry == "ghcr.io":
        # GitHub Container Registry - check via GitHub API
        ghcr_api_url = f"https://ghcr.io/v2/{image_path}/manifests/{tag}"

        # Try anonymous access first (public images)
        manifest_resp = await client.get(
            ghcr_api_url,
            headers={"Accept": accept_header},
        )

        if manifest_resp.status_code >= 500:
            raise GitHubServerError(f"GHCR returned {manifest_resp.status_code}")

        if manifest_resp.status_code == 429:
            retry_after = _parse_retry_after(manifest_resp.headers.get("Retry-After"))
            raise GitHubServerError("GHCR rate limited (429)", retry_after=retry_after)

        if manifest_resp.status_code == 200:
            return ValidationResult(
                is_valid=True,
                message=f"Found public GHCR image: ghcr.io/{image_path}:{tag}",
                username_match=True,
                repo_exists=True,
            )
        elif manifest_resp.status_code in [401, 403]:
            return ValidationResult(
                is_valid=False,
                message=(
                    f"Image 'ghcr.io/{image_path}' exists but is not public. "
                    "Please make it public in your GitHub package settings."
                ),
                username_match=True,
                repo_exists=True,
            )
        elif manifest_resp.status_code == 404:
            return ValidationResult(
                is_valid=False,
                message=(
                    f"Image 'ghcr.io/{image_path}:{tag}' not found. "
                    "Make sure it's pushed to GHCR."
                ),
                username_match=True,
                repo_exists=False,
            )
        else:
            return ValidationResult(
                is_valid=False,
                message=(
                    f"Could not verify GHCR image. Status: {manifest_resp.status_code}"
                ),
                username_match=True,
                repo_exists=False,
            )

    elif ".azurecr.io" in registry:
        # Azure Container Registry - we can't easily verify without credentials
        return ValidationResult(
            is_valid=True,
            message=(
                f"ACR image reference accepted: "
                f"{registry}/{image_path}:{tag}. "
                "Note: We cannot verify ACR images "
                "are public without credentials."
            ),
            username_match=True,
            repo_exists=True,
        )

    else:
        return ValidationResult(
            is_valid=False,
            message=(
                f"Unsupported container registry: {registry}. "
                "Please use Docker Hub, GHCR, or Azure ACR."
            ),
            username_match=False,
            repo_exists=False,
        )


async def validate_container_image(
    image_url: str,
    expected_username: str,
) -> ValidationResult:
    """
    Validate that a container image exists and is publicly accessible.

    Supports:
    - Docker Hub: username/image or docker.io/username/image
    - GitHub Container Registry: ghcr.io/username/image
    - Azure Container Registry: *.azurecr.io/image

    Args:
        image_url: The container image URL/reference
        expected_username: Expected username (for ownership verification)

    Returns:
        ValidationResult with details about the image

    RETRY: 3 attempts with exponential backoff + jitter for transient failures.
    CIRCUIT BREAKER: Opens after 5 consecutive failures, recovers after 60 seconds.
    """
    image_url = image_url.strip().lower()

    # Remove common prefixes
    if image_url.startswith("https://"):
        image_url = image_url[8:]
    if image_url.startswith("http://"):
        image_url = image_url[7:]

    # Parse the image reference
    # Docker Hub format: username/image:tag or docker.io/username/image:tag
    # GHCR format: ghcr.io/username/image:tag
    # ACR format: registryname.azurecr.io/image:tag

    registry = "docker.io"
    image_path = image_url
    tag = "latest"

    # Extract tag if present
    if ":" in image_path and "@" not in image_path:
        image_path, tag = image_path.rsplit(":", 1)

    # Determine registry
    if image_path.startswith("ghcr.io/"):
        registry = "ghcr.io"
        image_path = image_path[8:]  # Remove "ghcr.io/"
    elif image_path.startswith("docker.io/"):
        registry = "docker.io"
        image_path = image_path[10:]  # Remove "docker.io/"
    elif ".azurecr.io/" in image_path:
        # Azure Container Registry
        parts = image_path.split("/", 1)
        registry = parts[0]
        image_path = parts[1] if len(parts) > 1 else ""

    # Validate image path has at least username/image format for Docker Hub/GHCR
    if registry in ["docker.io", "ghcr.io"]:
        if "/" not in image_path:
            # Docker Hub library images (e.g., "python") - add library prefix
            if registry == "docker.io":
                image_path = f"library/{image_path}"
            else:
                return ValidationResult(
                    is_valid=False,
                    message="GHCR images must be in format: ghcr.io/username/image",
                    username_match=False,
                    repo_exists=False,
                )

        # Check username match for Docker Hub and GHCR
        image_username = image_path.split("/")[0]
        if image_username != "library":  # Skip check for official Docker images
            username_match = image_username == expected_username.lower()
            if not username_match:
                return ValidationResult(
                    is_valid=False,
                    message=(
                        f"Image owner '{image_username}' does not match "
                        f"your username '{expected_username}'"
                    ),
                    username_match=False,
                    repo_exists=False,
                )

    try:
        return await _check_container_image_with_retry(registry, image_path, tag)
    except RETRIABLE_EXCEPTIONS as e:
        logger.warning(f"All retries exhausted checking container image: {e}")
        return ValidationResult(
            is_valid=False,
            message="Container registry request failed. Please try again.",
            username_match=True,
            repo_exists=False,
        )
    except Exception as e:
        logger.exception(f"Unexpected error checking container image: {e}")
        return ValidationResult(
            is_valid=False,
            message=f"Unexpected error: {str(e)}",
            username_match=True,
            repo_exists=False,
        )
