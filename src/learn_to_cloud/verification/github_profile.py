"""Profile README and fork results from verified repository metadata.

Both checks run after the ownership preflight, which has already fetched the
repository from GitHub, so neither makes another request.
"""

from __future__ import annotations

from learn_to_cloud.schemas.verification import ValidationResult
from learn_to_cloud.verification.repository_ownership import OwnedRepository


def validate_profile_readme() -> ValidationResult:
    """Pass once ownership confirmed the learner's public profile repository."""
    return ValidationResult(
        is_valid=True,
        message="Profile README validated successfully!",
        username_match=True,
        repo_exists=True,
    )


def validate_repo_fork(repository: OwnedRepository) -> ValidationResult:
    """Confirm the owned repository forks the required upstream."""
    expected = repository.target.forked_from
    if expected is None:
        raise ValueError("Fork verification requires an upstream repository")
    parent = repository.parent
    if parent is None:
        message = "Repository is not a fork"
    elif parent.lower() != expected.lower():
        message = f"Forked from {parent}, not {expected}"
    else:
        return ValidationResult(
            is_valid=True,
            message=(
                f"Repository fork validated successfully! Verified fork of {expected}"
            ),
            username_match=True,
            repo_exists=True,
        )
    return ValidationResult(
        is_valid=False, message=message, username_match=True, repo_exists=True
    )
