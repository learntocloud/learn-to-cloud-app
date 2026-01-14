"""GitHub-specific validation utilities for hands-on verification.

This module handles all GitHub-specific validations including:
- GitHub profile verification
- Profile README verification
- Repository URL verification
- Repository fork verification
- GitHub URL parsing

For the main hands-on verification orchestration, see hands_on_verification.py
"""

import logging
import re
from dataclasses import dataclass

import httpx

from core.config import get_settings
from core.telemetry import track_dependency

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
    """
    url = url.strip().rstrip("/")

    if not url.startswith("https://github.com/"):
        return ParsedGitHubUrl(
            username="", is_valid=False, error="URL must start with https://github.com/"
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
async def check_github_url_exists(url: str) -> tuple[bool, str]:
    """
    Check if a GitHub URL exists by making a HEAD request.

    Returns:
        Tuple of (exists: bool, message: str)
    """
    settings = get_settings()
    try:
        async with httpx.AsyncClient(
            follow_redirects=True, timeout=settings.http_timeout
        ) as client:
            response = await client.head(url)

            if response.status_code == 200:
                return True, "URL exists"
            elif response.status_code == 404:
                return False, "URL not found (404)"
            else:
                return False, f"Unexpected status code: {response.status_code}"

    except httpx.TimeoutException:
        return False, "Request timed out"
    except httpx.RequestError as e:
        logger.warning(f"Error checking GitHub URL {url}: {e}")
        return False, f"Request error: {str(e)}"

@track_dependency("github_api_fork_check", "HTTP")
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
    """
    api_url = f"https://api.github.com/repos/{username}/{repo_name}"
    settings = get_settings()

    try:
        async with httpx.AsyncClient(timeout=settings.http_timeout) as client:
            response = await client.get(
                api_url,
                headers=_get_github_headers(),
            )

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
                    f"Repository is forked from {parent_full_name}, not {original_repo}",
                )

    except httpx.TimeoutException:
        return False, "GitHub API request timed out"
    except httpx.RequestError as e:
        logger.warning(f"Error checking fork status: {e}")
        return False, f"Request error: {str(e)}"

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
            message=f"GitHub username '{username}' does not match your account username '{expected_username}'",
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
            message=f"GitHub username '{parsed.username}' does not match your account username '{expected_username}'",
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
            message=f"GitHub username '{parsed.username}' does not match your account username '{expected_username}'",
            username_match=False,
            repo_exists=False,
        )

    if parsed.repo_name and parsed.repo_name.lower() != parsed.username.lower():
        return ValidationResult(
            is_valid=False,
            message=f"Profile README must be in a repo named '{parsed.username}', not '{parsed.repo_name}'",
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
            message=f"GitHub username '{parsed.username}' does not match your account username '{expected_username}'",
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
