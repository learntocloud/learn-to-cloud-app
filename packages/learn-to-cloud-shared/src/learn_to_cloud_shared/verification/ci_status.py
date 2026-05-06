"""CI status verification service.

Checks whether the learner's fork has a passing CI workflow on the
``main`` branch.  Instead of re-grading code, we trust the test suite
that ships with the upstream starter repository.

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

import httpx
from opentelemetry import trace

from learn_to_cloud_shared.schemas import ValidationResult
from learn_to_cloud_shared.verification.github_profile import (
    RETRIABLE_EXCEPTIONS,
    github_api_get,
    github_error_to_validation_result,
)

tracer = trace.get_tracer(__name__)

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
    with tracer.start_as_current_span(
        "ci_status_verification",
        attributes={
            "github.owner": owner,
            "github.repo": repo,
        },
    ) as span:
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
            if isinstance(e, httpx.HTTPStatusError) and e.response.status_code == 404:
                span.set_attribute("verification.passed", False)
                span.set_attribute("verification.reason", "workflow_not_found")
                return ValidationResult(
                    is_valid=False,
                    message=(
                        f"CI workflow not found in {owner}/{repo}. "
                        "Make sure you've synced your fork with the upstream "
                        "repository to get the .github/workflows/ci.yml file, "
                        "and that GitHub Actions is enabled on your fork."
                    ),
                )
            span.record_exception(e)
            return github_error_to_validation_result(
                e,
                event="ci_status.api_error",
                context={"owner": owner, "repo": repo},
            )

        data = response.json()
        runs: list[dict] = data.get("workflow_runs", [])

        if not runs:
            span.set_attribute("verification.passed", False)
            span.set_attribute("verification.reason", "no_runs")
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

        span.set_attribute("ci.status", status or "unknown")
        span.set_attribute("ci.conclusion", conclusion or "unknown")
        span.set_attribute("ci.run_number", run_number)

        # ── Still running ─────────────────────────────────────────────────
        if status != "completed":
            span.set_attribute("verification.passed", False)
            span.set_attribute("verification.reason", "still_running")
            return ValidationResult(
                is_valid=False,
                message=(
                    f"CI run #{run_number} is still {status}. "
                    "Wait for it to finish, then try again."
                ),
            )

        # ── Completed — check conclusion ──────────────────────────────────
        if conclusion == "success":
            span.set_attribute("verification.passed", True)
            return ValidationResult(
                is_valid=True,
                message=(
                    f"CI tests are passing on main (run #{run_number}). "
                    "Your Journal API implementation is verified!"
                ),
            )

        # CI ran but did not succeed
        span.set_attribute("verification.passed", False)
        span.set_attribute("verification.reason", f"conclusion:{conclusion}")
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
