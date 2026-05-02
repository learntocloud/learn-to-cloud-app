"""Pull Request verification service.

The PR URL is server-derived from the authenticated user's GitHub
username, the requirement's repo, and the submitted PR number.
No URL parsing or ownership checks are needed.

Architecture — fully deterministic:

  1. Fetch PR metadata → verify merged
  2. Fetch PR diff
  3. Run indicator engine → pass/fail

The indicator engine (``indicator_engine.py``) checks fail/pass
indicators deterministically.  Results are instant and reproducible.
"""

from __future__ import annotations

import httpx
from opentelemetry import trace

from learn_to_cloud.schemas import HandsOnRequirement, TaskResult, ValidationResult
from learn_to_cloud.services.verification.github_profile import (
    RETRIABLE_EXCEPTIONS,
    github_api_get,
    github_error_to_validation_result,
)
from learn_to_cloud.services.verification.indicator_engine import check_indicators

# Maximum diff size to prevent memory exhaustion (50 KB)
MAX_FILE_SIZE_BYTES: int = 50 * 1024

tracer = trace.get_tracer(__name__)

# Patterns that suggest prompt injection attempts in PR diffs.
# Logged as warnings for monitoring but do not affect pass/fail.
_SUSPICIOUS_PATTERNS = [
    "ignore previous instructions",
    "ignore all instructions",
    "mark as passed",
    "override",
    "system prompt",
]


async def _fetch_pr_data(owner: str, repo: str, pr_number: int) -> dict:
    """Fetch PR metadata."""
    url = f"https://api.github.com/repos/{owner}/{repo}/pulls/{pr_number}"
    return (await github_api_get(url)).json()


async def _fetch_pr_diff(owner: str, repo: str, pr_number: int) -> str:
    """Fetch the unified diff of a PR, size-limited."""
    url = f"https://api.github.com/repos/{owner}/{repo}/pulls/{pr_number}"
    resp = await github_api_get(
        url, extra_headers={"Accept": "application/vnd.github.diff"}
    )
    diff_text = resp.text

    if len(diff_text.encode("utf-8")) > MAX_FILE_SIZE_BYTES:
        diff_text = diff_text[: MAX_FILE_SIZE_BYTES // 2]
        diff_text += "\n\n[DIFF TRUNCATED - exceeded size limit]"

    diff_lower = diff_text.lower()
    for pattern in _SUSPICIOUS_PATTERNS:
        if pattern in diff_lower:
            span = trace.get_current_span()
            span.add_event(
                "suspicious_pattern_in_diff",
                {"pattern": pattern, "owner": owner, "pr": pr_number},
            )
            break

    return diff_text


async def validate_pr(
    pr_url: str,
    requirement: HandsOnRequirement,
) -> ValidationResult:
    """Validate a GitHub Pull Request submission.

    Fully deterministic.

    Steps:
      1. Parse the trusted PR URL
      2. Fetch PR metadata, verify it is merged
      3. Fetch the PR diff
      4. Run the indicator engine for pass/fail

    Args:
        pr_url: Server-derived PR URL (trusted).
        requirement: The requirement being verified.

    Returns:
        ValidationResult with pass/fail and a user-facing message.
    """
    # Extract owner/repo/number from trusted URL
    # Format: https://github.com/{owner}/{repo}/pull/{number}
    parts = pr_url.rstrip("/").split("/")
    owner = parts[3]
    repo = parts[4]
    pr_number = int(parts[6])

    with tracer.start_as_current_span(
        "pr_verification",
        attributes={
            "pr.url": pr_url,
            "pr.number": pr_number,
            "requirement.id": requirement.id,
            "github.owner": owner,
            "github.repo": repo,
        },
    ) as span:
        # ── Step 1: Fetch PR metadata ────────────────────────────
        try:
            pr_data = await _fetch_pr_data(owner, repo, pr_number)
        except (
            httpx.HTTPStatusError,
            *RETRIABLE_EXCEPTIONS,
        ) as e:
            if isinstance(e, httpx.HTTPStatusError) and e.response.status_code == 404:
                span.set_attribute("verification.passed", False)
                span.set_attribute("verification.reason", "pr_not_found")
                return ValidationResult(
                    is_valid=False,
                    message=(
                        f"Pull request #{pr_number} not found. "
                        "Check the PR number and try again."
                    ),
                )
            span.record_exception(e)
            return github_error_to_validation_result(
                e,
                event="pr_verification.api_error",
                context={"owner": owner, "repo": repo, "pr": pr_number},
            )

        # ── Step 2: Verify PR is merged ──────────────────────────
        if not pr_data.get("merged"):
            state = pr_data.get("state", "unknown")
            span.set_attribute("verification.passed", False)
            span.set_attribute("verification.reason", f"not_merged:{state}")
            fail_msg = (
                f"PR #{pr_number} is still open. "
                "Merge it into main first, then resubmit."
                if state == "open"
                else f"PR #{pr_number} was closed without "
                "merging. Create a new PR, merge it, "
                "then submit that link."
            )
            return ValidationResult(is_valid=False, message=fail_msg)

        branch = pr_data.get("head", {}).get("ref", "unknown")

        # ── Step 3: Fetch PR diff ────────────────────────────────
        try:
            diff = await _fetch_pr_diff(owner, repo, pr_number)
        except (
            httpx.HTTPStatusError,
            *RETRIABLE_EXCEPTIONS,
        ) as e:
            span.record_exception(e)
            return github_error_to_validation_result(
                e,
                event="pr_verification.diff_error",
                context={"owner": owner, "pr": pr_number},
            )

        # ── Step 4: Deterministic indicator check ────────────────
        indicator_result = check_indicators(diff, requirement)

        if not indicator_result.passed:
            if indicator_result.matched_fail:
                next_steps = f"Remove or replace: {indicator_result.matched_fail[0]}"
            elif indicator_result.missing_pass:
                next_steps = (
                    f"Missing implementation for: "
                    f"{', '.join(indicator_result.missing_pass[:3])}"
                )
            else:
                next_steps = "Review the requirement and try again."

            task_result = TaskResult(
                task_name=requirement.name,
                passed=False,
                feedback=indicator_result.reason,
                next_steps=next_steps,
            )

            span.set_attribute("verification.passed", False)
            span.set_attribute("verification.reason", "indicators_failed")

            return ValidationResult(
                is_valid=False,
                message=(
                    f"PR #{pr_number} was merged but doesn't "
                    f"fully implement the required task. "
                    f"Review the feedback below."
                ),
                username_match=True,
                task_results=[task_result],
            )

        # ── Passed ───────────────────────────────────────────────
        task_result = TaskResult(
            task_name=requirement.name,
            passed=True,
            feedback="All required implementation indicators verified.",
            next_steps="",
        )

        span.set_attribute("verification.passed", True)
        span.set_attribute("pr.branch", branch)

        return ValidationResult(
            is_valid=True,
            message=f"PR #{pr_number} verified! Merged from branch '{branch}'.",
            username_match=True,
            task_results=[task_result],
        )
