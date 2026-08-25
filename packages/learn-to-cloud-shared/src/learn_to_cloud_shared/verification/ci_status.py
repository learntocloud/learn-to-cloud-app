"""CI status verification service.

Checks whether the learner's fork has a passing CI workflow on the
``main`` branch.  Instead of re-grading code, we trust the test suite
that ships with the upstream starter repository.

The ``journal-starter`` repo includes a GitHub Actions workflow
(``.github/workflows/ci.yml``) with lint and test jobs.  When learners
fork, they inherit the workflow.  A green CI on ``main`` proves all
tests pass — which is the honest acceptance gate.

URL validation and ownership checks are handled by the engine gate
before this module is called.

Workflow::

    fetch latest workflow runs on main
        → check conclusion
        → ValidationResult

For the workflow-runs seam, see ``workflow_runs.py``.
"""

from __future__ import annotations

import httpx
from opentelemetry import trace

from learn_to_cloud_shared.schemas import ValidationResult
from learn_to_cloud_shared.verification.errors import github_error_to_result
from learn_to_cloud_shared.verification.github_http import (
    RETRIABLE_EXCEPTIONS,
)
from learn_to_cloud_shared.verification.workflow_runs import (
    WorkflowRuns,
    default_workflow_runs,
)

# The workflow filename in learntocloud/journal-starter.
_CI_WORKFLOW_FILE = "ci.yml"


async def verify_ci_status(
    owner: str,
    repo: str,
    runs: WorkflowRuns | None = None,
) -> ValidationResult:
    """Verify that CI tests pass on the learner's fork's main branch.

    URL validation and ownership checks are handled by the engine gate
    before this function is called.

    Args:
        owner: Repository owner (GitHub username).
        repo: Repository name.
        runs: Workflow-runs port (defaults to the production adapter).

    Returns:
        ``ValidationResult`` — valid when the most recent CI run on
        ``main`` has ``conclusion == "success"``.
    """
    runs = runs or default_workflow_runs()
    span = trace.get_current_span()
    try:
        latest_run = await runs.latest_run(owner, repo, _CI_WORKFLOW_FILE)
    except (
        httpx.HTTPStatusError,
        *RETRIABLE_EXCEPTIONS,
    ) as e:
        if isinstance(e, httpx.HTTPStatusError) and e.response.status_code == 404:
            span.set_attribute("http.response.status_code", 404)
            span.add_event("ci.workflow_not_found")
            return ValidationResult(
                is_valid=False,
                message=(
                    f"CI workflow not found in {owner}/{repo}. "
                    "Make sure you've synced your fork with the upstream "
                    "repository to get the .github/workflows/ci.yml file, "
                    "and that GitHub Actions is enabled on your fork."
                ),
            )
        return github_error_to_result(
            e,
            event="ci_status.api_error",
        )

    if latest_run is None:
        span.add_event("ci.no_runs")
        return ValidationResult(
            is_valid=False,
            message=(
                "No CI runs found on the main branch. "
                "Push a commit to main or merge a PR to trigger "
                "the CI workflow, then try again."
            ),
        )

    conclusion = latest_run.get("conclusion")
    status = latest_run.get("status")
    run_url = latest_run.get("html_url", "")
    run_number = latest_run.get("run_number", 0)

    if status != "completed":
        span.add_event("ci.still_running")
        return ValidationResult(
            is_valid=False,
            message=(
                f"CI run #{run_number} is still {status}. "
                "Wait for it to finish, then try again."
            ),
        )

    if conclusion == "success":
        span.add_event("ci.passed")
        return ValidationResult(
            is_valid=True,
            message=(
                f"CI tests are passing on main (run #{run_number}). "
                "Your Journal API implementation is verified!"
            ),
        )

    span.add_event("ci.failed")
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
