"""Shared utilities for verification services.

GitHub URL parsing, ownership validation, feedback sanitization,
and the base VerificationError exception.
"""

from __future__ import annotations

import logging
import re
from urllib.parse import urlparse

from learn_to_cloud.schemas import ValidationResult

logger = logging.getLogger(__name__)


class VerificationError(Exception):
    """Base exception for verification failures.

    Attributes:
        retriable: ``True`` when the caller should retry (transient error).
    """

    def __init__(self, message: str, retriable: bool = False):
        super().__init__(message)
        self.retriable = retriable


def extract_repo_info(repo_url: str) -> tuple[str, str]:
    """Extract owner and repo name from a GitHub URL.

    Handles common variants: ``https://``, ``http://``, ``www.github.com``,
    trailing slashes, ``.git`` suffixes, sub-paths, query strings, and
    fragment identifiers.

    Raises:
        ValueError: If *repo_url* is not a valid GitHub repository URL.
    """
    url = repo_url.strip()
    if not url:
        raise ValueError(f"Invalid GitHub repository URL: {repo_url}")

    if not url.startswith(("http://", "https://")):
        url = "https://" + url

    parsed = urlparse(url)
    host = (parsed.hostname or "").lower()

    if host not in ("github.com", "www.github.com"):
        raise ValueError(f"Invalid GitHub repository URL: {repo_url}")

    segments = [s for s in parsed.path.split("/") if s]
    if len(segments) < 2:
        raise ValueError(f"Invalid GitHub repository URL: {repo_url}")

    owner = segments[0]
    repo = segments[1].removesuffix(".git")

    return owner, repo


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


def sanitize_feedback(feedback: str | None) -> str:
    """Sanitize feedback before displaying to users.

    Removes HTML tags, code blocks, and URLs.
    """
    if not feedback or not isinstance(feedback, str):
        return "No feedback provided"

    max_length = 500
    if len(feedback) > max_length:
        feedback = feedback[:max_length].rsplit(" ", 1)[0] + "..."

    feedback = re.sub(r"<[^>]+>", "", feedback)
    feedback = re.sub(r"```[\s\S]*?```", "[code snippet]", feedback)
    feedback = re.sub(r"https?://\S+", "[link removed]", feedback)

    return feedback.strip() or "No feedback provided"
