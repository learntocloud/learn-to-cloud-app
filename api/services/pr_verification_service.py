"""Pull Request verification service.

Deterministic verification that a learner submitted work via a merged
GitHub Pull Request that touched the expected files.  No LLM calls —
uses the GitHub API only.

Verification checks:
1. URL is a valid GitHub PR link (owner/repo/pull/N)
2. PR belongs to the learner's fork (owner matches GitHub username)
3. PR is merged (not just opened or closed-without-merge)
4. PR changed at least one of the expected files for the task

Used by Phase 3 to enforce the branching/PR development workflow
described in the journal-starter README.
"""

from __future__ import annotations

import logging
import re

import httpx
from circuitbreaker import CircuitBreakerError, circuit
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential_jitter,
)

from schemas import HandsOnRequirement, ValidationResult
from services.github_hands_on_verification_service import (
    RETRIABLE_EXCEPTIONS,
    GitHubServerError,
    _get_github_client,
    _get_github_headers,
)

logger = logging.getLogger(__name__)

# Regex to parse PR URLs like https://github.com/user/repo/pull/42
_PR_URL_PATTERN = re.compile(
    r"^https?://github\.com/(?P<owner>[^/]+)/(?P<repo>[^/]+)/pull/(?P<number>\d+)",
    re.IGNORECASE,
)


class ParsedPrUrl:
    """Parsed components of a GitHub PR URL."""

    __slots__ = ("owner", "repo", "number", "error")

    def __init__(
        self,
        owner: str = "",
        repo: str = "",
        number: int = 0,
        error: str | None = None,
    ):
        self.owner = owner
        self.repo = repo
        self.number = number
        self.error = error

    @property
    def is_valid(self) -> bool:
        return self.error is None


def parse_pr_url(url: str) -> ParsedPrUrl:
    """Parse a GitHub Pull Request URL.

    Accepts:
        https://github.com/owner/repo/pull/42
        https://github.com/owner/repo/pull/42/files
        https://github.com/owner/repo/pull/42/commits
    """
    url = url.strip().rstrip("/")

    match = _PR_URL_PATTERN.match(url)
    if not match:
        return ParsedPrUrl(
            error=(
                "URL must be a GitHub Pull Request link "
                "(e.g., https://github.com/username/journal-starter/pull/1)"
            ),
        )

    return ParsedPrUrl(
        owner=match.group("owner"),
        repo=match.group("repo"),
        number=int(match.group("number")),
    )


@circuit(
    failure_threshold=5,
    recovery_timeout=60,
    expected_exception=RETRIABLE_EXCEPTIONS,
    name="github_pr_circuit",
)
@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential_jitter(initial=0.5, max=10),
    retry=retry_if_exception_type(RETRIABLE_EXCEPTIONS),
    reraise=True,
)
async def _fetch_pr_data(owner: str, repo: str, pr_number: int) -> dict:
    """Fetch PR metadata from the GitHub API with retry + circuit breaker.

    Returns the JSON response dict.

    Raises:
        GitHubServerError: On 5xx or 429 responses (triggers retry).
        httpx.HTTPStatusError: On non-retriable HTTP errors.
    """
    api_url = f"https://api.github.com/repos/{owner}/{repo}/pulls/{pr_number}"
    client = await _get_github_client()
    response = await client.get(api_url, headers=_get_github_headers())

    if response.status_code >= 500:
        raise GitHubServerError(f"GitHub API returned {response.status_code}")

    if response.status_code == 429:
        raise GitHubServerError("GitHub rate limited (429)")

    response.raise_for_status()
    return response.json()


@circuit(
    failure_threshold=5,
    recovery_timeout=60,
    expected_exception=RETRIABLE_EXCEPTIONS,
    name="github_pr_files_circuit",
)
@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential_jitter(initial=0.5, max=10),
    retry=retry_if_exception_type(RETRIABLE_EXCEPTIONS),
    reraise=True,
)
async def _fetch_pr_files(owner: str, repo: str, pr_number: int) -> list[str]:
    """Fetch the list of files changed in a PR.

    Returns a list of file paths.

    Paginates up to 100 files (GitHub default), which is more than enough
    for the journal-starter tasks.
    """
    api_url = f"https://api.github.com/repos/{owner}/{repo}/pulls/{pr_number}/files"
    client = await _get_github_client()
    response = await client.get(
        api_url,
        headers=_get_github_headers(),
        params={"per_page": 100},
    )

    if response.status_code >= 500:
        raise GitHubServerError(f"GitHub API returned {response.status_code}")

    if response.status_code == 429:
        raise GitHubServerError("GitHub rate limited (429)")

    response.raise_for_status()

    return [f["filename"] for f in response.json()]


async def validate_pr(
    pr_url: str,
    expected_username: str,
    requirement: HandsOnRequirement,
) -> ValidationResult:
    """Validate a GitHub Pull Request submission.

    Checks:
    1. URL is a valid PR link
    2. PR owner matches the learner's GitHub username
    3. PR is merged
    4. PR touched at least one of the expected files (if configured)

    Args:
        pr_url: The submitted PR URL.
        expected_username: The learner's GitHub username from OAuth.
        requirement: The requirement being verified (contains expected_files).

    Returns:
        ValidationResult with pass/fail and a user-facing message.
    """
    parsed = parse_pr_url(pr_url)
    if not parsed.is_valid:
        return ValidationResult(
            is_valid=False,
            message=parsed.error or "Invalid PR URL",
            username_match=False,
        )

    # Check owner matches authenticated user
    if parsed.owner.lower() != expected_username.lower():
        return ValidationResult(
            is_valid=False,
            message=(
                f"PR owner '{parsed.owner}' does not match your GitHub "
                f"username '{expected_username}'. Submit a PR from your own fork."
            ),
            username_match=False,
        )

    # Fetch PR data from GitHub API
    try:
        pr_data = await _fetch_pr_data(parsed.owner, parsed.repo, parsed.number)
    except CircuitBreakerError:
        logger.error(
            "pr_verification.circuit_open",
            extra={"owner": parsed.owner, "repo": parsed.repo, "pr": parsed.number},
        )
        return ValidationResult(
            is_valid=False,
            message="GitHub service temporarily unavailable. Please try again later.",
            server_error=True,
        )
    except httpx.HTTPStatusError as e:
        if e.response.status_code == 404:
            return ValidationResult(
                is_valid=False,
                message=(
                    f"Pull request #{parsed.number} not found in "
                    f"{parsed.owner}/{parsed.repo}. Check the URL and try again."
                ),
                username_match=True,
            )
        logger.warning(
            "pr_verification.api_error",
            extra={
                "owner": parsed.owner,
                "repo": parsed.repo,
                "pr": parsed.number,
                "status": e.response.status_code,
            },
        )
        return ValidationResult(
            is_valid=False,
            message=f"GitHub API error ({e.response.status_code}). Try again later.",
            server_error=True,
        )
    except RETRIABLE_EXCEPTIONS as e:
        logger.warning(
            "pr_verification.request_error",
            extra={
                "owner": parsed.owner,
                "repo": parsed.repo,
                "pr": parsed.number,
                "error": str(e),
            },
        )
        return ValidationResult(
            is_valid=False,
            message="Could not reach GitHub. Please try again later.",
            server_error=True,
        )

    # Check PR is merged
    if not pr_data.get("merged"):
        state = pr_data.get("state", "unknown")
        if state == "open":
            return ValidationResult(
                is_valid=False,
                message=(
                    f"PR #{parsed.number} is still open. "
                    "Merge it into main first, then resubmit."
                ),
                username_match=True,
            )
        return ValidationResult(
            is_valid=False,
            message=(
                f"PR #{parsed.number} was closed without merging. "
                "Create a new PR, merge it, then submit that link."
            ),
            username_match=True,
        )

    # Check PR files (if expected_files configured on the requirement)
    expected_files = requirement.expected_files
    if expected_files:
        try:
            changed_files = await _fetch_pr_files(
                parsed.owner, parsed.repo, parsed.number
            )
        except CircuitBreakerError:
            logger.error(
                "pr_verification.files_circuit_open",
                extra={
                    "owner": parsed.owner,
                    "repo": parsed.repo,
                    "pr": parsed.number,
                },
            )
            return ValidationResult(
                is_valid=False,
                message=(
                    "GitHub service temporarily unavailable. " "Please try again later."
                ),
                server_error=True,
            )
        except (httpx.HTTPStatusError, *RETRIABLE_EXCEPTIONS) as e:
            logger.warning(
                "pr_verification.files_error",
                extra={
                    "owner": parsed.owner,
                    "repo": parsed.repo,
                    "pr": parsed.number,
                    "error": str(e),
                },
            )
            return ValidationResult(
                is_valid=False,
                message="Could not fetch PR file list. Please try again later.",
                server_error=True,
            )

        # Check if ANY expected file was modified in the PR
        changed_set = {f.lower() for f in changed_files}
        expected_set = {f.lower() for f in expected_files}
        matched = changed_set & expected_set

        if not matched:
            expected_display = ", ".join(f"`{f}`" for f in expected_files)
            return ValidationResult(
                is_valid=False,
                message=(
                    f"PR #{parsed.number} was merged but didn't modify "
                    f"the expected file(s): {expected_display}. "
                    "Make sure you submit the PR for the correct task."
                ),
                username_match=True,
            )

    branch_name = pr_data.get("head", {}).get("ref", "unknown")
    pr_title = pr_data.get("title", "")

    logger.info(
        "pr_verification.passed",
        extra={
            "owner": parsed.owner,
            "repo": parsed.repo,
            "pr": parsed.number,
            "branch": branch_name,
            "title": pr_title,
        },
    )

    return ValidationResult(
        is_valid=True,
        message=(
            f"PR #{parsed.number} verified! " f"Merged from branch '{branch_name}'."
        ),
        username_match=True,
    )
