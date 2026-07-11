"""GitHub-specific validation for hands-on verification.

Validates the learner's GitHub profile, profile README repository, and repo
forks. Each validator receives the ``GitHubTarget`` constructed from the
learner's username plus the requirement (see ``submission_derivation``), so it
checks existence and fork lineage without parsing a URL back into an identity.

For the GitHub HTTP plumbing (retry, headers, error mapping), see
``github_http.py``. For the existence/metadata seam these validators build on,
see ``github_metadata.py``.
"""

from __future__ import annotations

import httpx
from opentelemetry import trace

from learn_to_cloud_shared.github_target import GitHubTarget
from learn_to_cloud_shared.schemas import ValidationResult
from learn_to_cloud_shared.verification.github_http import (
    RETRIABLE_EXCEPTIONS,
    github_error_to_validation_result,
)
from learn_to_cloud_shared.verification.github_metadata import (
    GitHubMetadata,
    default_github_metadata,
)

__all__ = [
    "GitHubMetadata",
    "RETRIABLE_EXCEPTIONS",
    "check_github_url_exists",
    "check_repo_is_fork_of",
    "default_github_metadata",
    "github_error_to_validation_result",
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
    except httpx.HTTPStatusError as e:
        span = trace.get_current_span()
        span.record_exception(e)
        return github_error_to_validation_result(
            e,
            event="fork_check.api_error",
            context={"username": username, "repo": repo_name},
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
    target: GitHubTarget,
    metadata: GitHubMetadata | None = None,
) -> ValidationResult:
    """Confirm the learner's GitHub profile page exists.

    The profile is built from the authenticated username, so the identity is
    guaranteed by construction; this only checks that the page resolves.
    """
    result = await check_github_url_exists(target.url, metadata)
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
        message=f"GitHub profile verified for @{target.owner}",
        username_match=True,
        repo_exists=True,
    )


async def validate_profile_readme(
    target: GitHubTarget,
    metadata: GitHubMetadata | None = None,
) -> ValidationResult:
    """Confirm the learner's profile README repository exists.

    The repository lives at ``<username>/<username>`` by construction, so this
    only checks that it resolves.
    """
    result = await check_github_url_exists(target.url, metadata)
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
    target: GitHubTarget,
    metadata: GitHubMetadata | None = None,
) -> ValidationResult:
    """Confirm the learner's repository is a fork of the required upstream.

    The fork identity (``<username>/<fork-name>``) and the upstream it must
    descend from (``target.forked_from``) are both known by construction, so
    this only verifies the fork lineage against GitHub.
    """
    if not target.repo or not target.forked_from:
        return ValidationResult(
            is_valid=False,
            message="Requirement configuration error: missing required_repo",
            username_match=True,
            repo_exists=False,
        )

    fork_result = await check_repo_is_fork_of(
        target.owner, target.repo, target.forked_from, metadata
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
