"""Shared ownership preflight for repository-based verification."""

import logging
import re
from json import JSONDecodeError

import httpx

from learn_to_cloud_shared.github_target import GitHubTarget
from learn_to_cloud_shared.schemas import ValidationResult
from learn_to_cloud_shared.verification.errors import github_error_to_result
from learn_to_cloud_shared.verification.github_http import RETRIABLE_EXCEPTIONS
from learn_to_cloud_shared.verification.github_metadata import (
    GitHubMetadata,
    default_github_metadata,
)

logger = logging.getLogger(__name__)


def _valid_path_segment(value: object) -> bool:
    return (
        isinstance(value, str)
        and 0 < len(value) <= 255
        and value not in {".", ".."}
        and re.fullmatch(r"[A-Za-z0-9_.-]+", value) is not None
    )


def _invalid_metadata() -> ValidationResult:
    logger.warning(
        "github.ownership.invalid_metadata",
        extra={"error.type": "response_validation"},
    )
    return ValidationResult(
        is_valid=False,
        message="GitHub returned an unexpected response. Please try again later.",
        verification_completed=False,
    )


async def check_repository_ownership(
    target: GitHubTarget,
    user_id: int,
    metadata: GitHubMetadata | None = None,
) -> GitHubTarget | ValidationResult:
    """Return the owned public repository's canonical target or a failed check."""
    if not target.repo:
        raise ValueError("Repository ownership requires a repository target")
    metadata = metadata or default_github_metadata()
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
                "The required public repository could not be found or accessed. "
                "Make sure it exists under your GitHub account and is public. "
                "If you changed your GitHub username, sign out, sign in again, "
                "and submit a new attempt."
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
        or not _valid_path_segment(login)
        or not isinstance(name, str)
        or not _valid_path_segment(name)
        or not isinstance(private, bool)
    ):
        return _invalid_metadata()
    if owner_id != user_id:
        return ValidationResult(
            is_valid=False,
            message=(
                "This repository must belong to the GitHub account you signed "
                "in with. If you changed your GitHub username, sign out, sign "
                "in again, and submit a new attempt. Otherwise, use the "
                "required repository under your own account."
            ),
            username_match=False,
            repo_exists=True,
        )
    if private:
        return ValidationResult(
            is_valid=False,
            message="Make the required repository public, then submit a new attempt.",
            username_match=True,
            repo_exists=True,
        )
    return GitHubTarget(owner=login, repo=name, forked_from=target.forked_from)
