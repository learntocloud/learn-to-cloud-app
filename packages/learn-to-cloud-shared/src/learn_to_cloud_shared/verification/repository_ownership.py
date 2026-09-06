"""Shared ownership preflight for repository-based verification."""

import logging
from json import JSONDecodeError

import httpx

from learn_to_cloud_shared.github_repository_target import GitHubRepositoryTarget
from learn_to_cloud_shared.schemas import ValidationResult
from learn_to_cloud_shared.verification.errors import github_error_to_result
from learn_to_cloud_shared.verification.github_http import RETRIABLE_EXCEPTIONS
from learn_to_cloud_shared.verification.github_metadata import (
    GitHubApiMetadata,
    GitHubMetadata,
)

logger = logging.getLogger(__name__)


def _invalid_metadata() -> ValidationResult:
    logger.warning(
        "github.ownership.invalid_metadata",
        extra={"error.type": "response_validation"},
    )
    return ValidationResult(
        is_valid=False,
        message="Couldn't read GitHub's response. Try again later.",
        verification_completed=False,
    )


async def check_repository_ownership(
    target: GitHubRepositoryTarget,
    user_id: int,
    metadata: GitHubMetadata | None = None,
) -> GitHubRepositoryTarget | ValidationResult:
    """Return the owned public repository's canonical target or a failed check."""
    metadata = metadata or GitHubApiMetadata()
    try:
        data = await metadata.repo_metadata(target.owner, target.repo)
    except (JSONDecodeError, UnicodeDecodeError):
        return _invalid_metadata()
    except (httpx.HTTPStatusError, *RETRIABLE_EXCEPTIONS) as exc:
        return github_error_to_result(exc, event="github.ownership.api_error")

    if data is None:
        return ValidationResult(
            is_valid=False,
            message=(
                "Can't access the required repository. "
                "Make sure it's public and under your GitHub account. "
                "If you changed your GitHub username, sign out and back in, "
                "then resubmit."
            ),
            repo_exists=False,
        )
    owner = data.get("owner") if isinstance(data, dict) else None
    if not isinstance(owner, dict):
        return _invalid_metadata()
    owner_id = owner.get("id")
    login = owner.get("login")
    name = data.get("name")
    private = data.get("private")
    if (
        not isinstance(owner_id, int)
        or isinstance(owner_id, bool)
        or not 0 < owner_id <= 2**63 - 1
        or not isinstance(login, str)
        or not isinstance(name, str)
        or not isinstance(private, bool)
    ):
        return _invalid_metadata()
    if owner_id != user_id:
        return ValidationResult(
            is_valid=False,
            message=(
                "Use the required repository under the GitHub account you signed "
                "in with. If you changed your GitHub username, sign out and back "
                "in, then resubmit."
            ),
            username_match=False,
            repo_exists=True,
        )
    if private:
        return ValidationResult(
            is_valid=False,
            message="Make the required repository public, then resubmit.",
            username_match=True,
            repo_exists=True,
        )
    return GitHubRepositoryTarget(
        owner=login, repo=name, forked_from=target.forked_from
    )
