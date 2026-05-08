"""Shared utilities for verification services.

GitHub URL parsing, ownership validation, and the base
VerificationError exception.
"""

from __future__ import annotations

import logging
import re
from urllib.parse import urlparse

from learn_to_cloud_shared.schemas import ParsedGitHubUrl, ValidationResult

logger = logging.getLogger(__name__)

# GitHub usernames: 1-39 chars, alphanumeric + hyphen, can't start/end with hyphen
_GITHUB_USERNAME_RE = re.compile(r"^[a-zA-Z0-9](?:[a-zA-Z0-9-]*[a-zA-Z0-9])?$")
_MAX_USERNAME_LENGTH = 39


class VerificationError(Exception):
    """Base exception for verification failures.

    Attributes:
        retriable: ``True`` when the caller should retry (transient error).
    """

    def __init__(self, message: str, retriable: bool = False):
        super().__init__(message)
        self.retriable = retriable


def parse_github_url(url: str) -> ParsedGitHubUrl:
    """Parse a GitHub URL and extract username, repo, and file path.

    Handles common variants: ``https://``, ``http://``, ``www.github.com``,
    bare ``github.com/...``, trailing slashes, ``.git`` suffixes, query
    strings, and fragment identifiers.

    Recognises ``/blob/<branch>/<path>`` and ``/tree/<branch>/<path>``
    sub-paths and returns ``file_path`` for the former.
    """
    url = (url or "").strip()
    if not url:
        return ParsedGitHubUrl(
            username="",
            is_valid=False,
            error="URL must be a GitHub URL (e.g., https://github.com/username/repo)",
        )

    if not url.startswith(("http://", "https://")):
        url = "https://" + url

    parsed = urlparse(url)
    host = (parsed.hostname or "").lower()

    if host not in ("github.com", "www.github.com"):
        return ParsedGitHubUrl(
            username="",
            is_valid=False,
            error="URL must be a GitHub URL (e.g., https://github.com/username/repo)",
        )

    segments = [s for s in parsed.path.split("/") if s]
    if not segments:
        return ParsedGitHubUrl(
            username="", is_valid=False, error="Could not extract username from URL"
        )

    username = segments[0]
    if len(username) > _MAX_USERNAME_LENGTH or not _GITHUB_USERNAME_RE.match(username):
        return ParsedGitHubUrl(
            username=username, is_valid=False, error="Invalid GitHub username format"
        )

    repo_name = segments[1].removesuffix(".git") if len(segments) > 1 else None

    file_path = None
    if len(segments) > 4 and segments[2] == "blob":
        file_path = "/".join(segments[4:])

    return ParsedGitHubUrl(
        username=username, repo_name=repo_name, file_path=file_path, is_valid=True
    )


def extract_repo_info(repo_url: str) -> tuple[str, str]:
    """Extract owner and repo name from a GitHub URL.

    Raises:
        ValueError: If *repo_url* is not a valid GitHub repository URL.
    """
    parsed = parse_github_url(repo_url)
    if not parsed.is_valid or not parsed.repo_name:
        raise ValueError(f"Invalid GitHub repository URL: {repo_url}")
    return parsed.username, parsed.repo_name


def validate_repo_url(
    repo_url: str,
    github_username: str,
    expected_repo_name: str | None = None,
) -> tuple[str, str] | ValidationResult:
    """Parse a GitHub URL and verify the repo belongs to *github_username*."""
    try:
        owner, repo = extract_repo_info(repo_url)
    except ValueError as e:
        return ValidationResult(is_valid=False, message=str(e))

    if owner.lower() != github_username.lower():
        return ValidationResult(
            is_valid=False,
            message=(
                f"Repository owner '{owner}' does not match your GitHub username "
                f"'{github_username}'. Please submit your own repository."
            ),
            username_match=False,
        )

    if expected_repo_name is not None and repo.lower() != expected_repo_name.lower():
        return ValidationResult(
            is_valid=False,
            message=(
                f"Repository '{repo}' does not match the expected fork name "
                f"'{expected_repo_name}'. Submit the fork from the phase's "
                "upstream project."
            ),
            username_match=True,
        )

    return owner, repo
