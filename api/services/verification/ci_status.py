"""CI status verification service.

Checks whether the learner's fork has a passing CI workflow on the
``main`` branch.  This replaces the previous LLM-based code analysis
service: instead of re-grading code with a language model, we trust
the test suite that ships with the upstream starter repository.

The ``journal-starter`` repo includes a GitHub Actions workflow
(``.github/workflows/ci.yml``) with lint and test jobs.  When learners
fork, they inherit the workflow.  A green CI on ``main`` proves all
tests pass — which is the honest acceptance gate.

URL validation and ownership checks are handled by the dispatcher
before this module is called.

Workflow::

    fetch latest workflow runs on main
        → check conclusion
        → ValidationResult

For GitHub API helpers, see ``github_profile.py``.
"""

from __future__ import annotations

import logging

import httpx

from schemas import ValidationResult
from services.verification.github_profile import (
    RETRIABLE_EXCEPTIONS,
    github_api_get,
    github_error_to_validation_result,
)

logger = logging.getLogger(__name__)

# The workflow filename in learntocloud/journal-starter.
_CI_WORKFLOW_FILE = "ci.yml"


async def verify_ci_status(
    owner: str,
    repo: str,
) -> ValidationResult:
    """Verify that CI tests pass on the learner's fork's main branch.

    URL validation and ownership checks are handled by the dispatcher
    before this function is called.

    Args:
        owner: Repository owner (GitHub username).
        repo: Repository name.

    Returns:
        ``ValidationResult`` — valid when the most recent CI run on
        ``main`` has ``conclusion == "success"``.
    """
    logger.info(
        "ci_status.started",
        extra={"owner": owner, "repo": repo},
    )

    # ── Fetch latest CI workflow runs on main ─────────────────────────
    url = (
        f"https://api.github.com/repos/{owner}/{repo}"
        f"/actions/workflows/{_CI_WORKFLOW_FILE}/runs"
    )
    params = {"branch": "main", "per_page": 1}

    try:
        response = await github_api_get(url, params=params)
    except (
        httpx.HTTPStatusError,
        *RETRIABLE_EXCEPTIONS,
    ) as e:
        # A 404 here means the workflow file doesn't exist (not synced
        # from upstream) rather than the repo not existing.
        if isinstance(e, httpx.HTTPStatusError) and e.response.status_code == 404:
            logger.info(
                "ci_status.workflow_not_found",
                extra={"owner": owner, "repo": repo},
            )
            return ValidationResult(
                is_valid=False,
                message=(
                    f"CI workflow not found in {owner}/{repo}. "
                    "Make sure you've synced your fork with the upstream "
                    "repository to get the .github/workflows/ci.yml file, "
                    "and that GitHub Actions is enabled on your fork."
                ),
            )
        return github_error_to_validation_result(
            e,
            event="ci_status.api_error",
            context={"owner": owner, "repo": repo},
        )

    data = response.json()
    runs: list[dict] = data.get("workflow_runs", [])

    if not runs:
        logger.info(
            "ci_status.no_runs",
            extra={"owner": owner, "repo": repo},
        )
        return ValidationResult(
            is_valid=False,
            message=(
                "No CI runs found on the main branch. "
                "Push a commit to main or merge a PR to trigger "
                "the CI workflow, then try again."
            ),
        )

    latest_run = runs[0]
    conclusion = latest_run.get("conclusion")
    status = latest_run.get("status")
    run_url = latest_run.get("html_url", "")
    run_number = latest_run.get("run_number", 0)

    logger.info(
        "ci_status.run_found",
        extra={
            "owner": owner,
            "repo": repo,
            "status": status,
            "conclusion": conclusion,
            "run_number": run_number,
        },
    )

    # ── Still running ─────────────────────────────────────────────────
    if status != "completed":
        return ValidationResult(
            is_valid=False,
            message=(
                f"CI run #{run_number} is still {status}. "
                "Wait for it to finish, then try again."
            ),
        )

    # ── Completed — check conclusion ──────────────────────────────────
    if conclusion == "success":
        logger.info(
            "ci_status.passed",
            extra={"owner": owner, "repo": repo, "run_number": run_number},
        )
        return ValidationResult(
            is_valid=True,
            message=(
                f"CI tests are passing on main (run #{run_number}). "
                "Your Journal API implementation is verified!"
            ),
        )

    # CI ran but did not succeed
    logger.info(
        "ci_status.failed",
        extra={
            "owner": owner,
            "repo": repo,
            "conclusion": conclusion,
            "run_number": run_number,
        },
    )
    return ValidationResult(
        is_valid=False,
        message=(
            f"CI run #{run_number} finished with "
            f"conclusion '{conclusion}'. "
            f"Check the run details at {run_url} "
            "to see which tests are failing, fix them, "
            "and push to main."
        ),
    )
