"""GitHub-specific validation utilities for hands-on verification.

This module handles all GitHub-specific validations including:
- GitHub profile verification (Phase 0)
- Profile README verification (Phase 1)
- Repository fork verification (Phase 1)

For URL parsing, see ``repo_utils.parse_github_url``.
For the GitHub HTTP plumbing (retry, headers, error mapping), see
``github_http.py``. For the existence/metadata seam these validators build
on, see ``github_metadata.py``.
For the main hands-on verification orchestration, see hands_on_verification.py
"""

from opentelemetry import trace

from learn_to_cloud_shared.schemas import ValidationResult
from learn_to_cloud_shared.verification.github_http import (
    RETRIABLE_EXCEPTIONS,
    github_error_to_validation_result,
)
from learn_to_cloud_shared.verification.github_metadata import (
    GitHubMetadata,
    default_github_metadata,
)
from learn_to_cloud_shared.verification.repo_utils import parse_github_url

__all__ = [
    "GitHubMetadata",
    "RETRIABLE_EXCEPTIONS",
    "check_github_url_exists",
    "check_repo_is_fork_of",
    "default_github_metadata",
    "github_error_to_validation_result",
    "parse_github_url",
    "validate_github_profile",
    "validate_profile_readme",
    "validate_repo_fork",
]


async def check_github_url_exists(
    url: str, metadata: GitHubMetadata | None = None
) -> ValidationResult:
    """Check if a GitHub URL exists by making a HEAD request.

    Returns:
        ValidationResult with is_valid=True if URL exists.
        verification_completed=False when the failure is infrastructure-related
        (network error, GitHub outage) so callers can
        avoid penalising the user.

    RETRY: 3 attempts with exponential backoff + jitter for transient failures.
    """
    metadata = metadata or default_github_metadata()
    try:
        exists = await metadata.url_exists(url)
        return ValidationResult(
            is_valid=exists,
            message="URL exists" if exists else "URL not found (404)",
        )
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


async def check_repo_is_fork_of(
    username: str,
    repo_name: str,
    original_repo: str,
    metadata: GitHubMetadata | None = None,
) -> ValidationResult:
    """Check if a repository is a fork of the specified original repository.

    Args:
        username: The GitHub username
        repo_name: The repository name
        original_repo: The original repo in format "owner/repo"
        metadata: GitHub metadata port (defaults to the production adapter)

    Returns:
        ValidationResult with is_valid=True if repo is a fork of original_repo.
        verification_completed=False when the failure is infrastructure-related.

    RETRY: 3 attempts with exponential backoff + jitter for transient failures.
    """
    metadata = metadata or default_github_metadata()
    try:
        repo_data = await metadata.repo_metadata(username, repo_name)
        if repo_data is None:
            return ValidationResult(
                is_valid=False,
                message=f"Repository {username}/{repo_name} not found",
            )
        if not repo_data.get("fork", False):
            return ValidationResult(is_valid=False, message="Repository is not a fork")
        parent = repo_data.get("parent", {})
        parent_full_name = parent.get("full_name", "")
        if parent_full_name.lower() == original_repo.lower():
            return ValidationResult(
                is_valid=True, message=f"Verified fork of {original_repo}"
            )
        return ValidationResult(
            is_valid=False,
            message=f"Forked from {parent_full_name}, not {original_repo}",
        )
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
    github_url: str,
    expected_username: str,
    metadata: GitHubMetadata | None = None,
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
    result = await check_github_url_exists(profile_url, metadata)

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
    github_url: str,
    expected_username: str,
    metadata: GitHubMetadata | None = None,
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

    result = await check_github_url_exists(github_url, metadata)

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
    github_url: str,
    expected_username: str,
    required_repo: str,
    metadata: GitHubMetadata | None = None,
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
        parsed.username, parsed.repo_name, required_repo, metadata
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
