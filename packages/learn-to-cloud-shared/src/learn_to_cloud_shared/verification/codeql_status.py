"""CodeQL status verification service (Phase 6).

Checks whether the learner's fork runs GitHub CodeQL code scanning and that
it is **green on the current tip of ``main``**. Like Phase 3's CI gate, we
trust an objective GitHub signal instead of re-grading: a successful run of
the learner's committed CodeQL workflow on the exact commit at ``main`` HEAD.

Design notes:
  * **Tokenless.** We use the public workflow-runs endpoint (via the
    ``WorkflowRuns`` seam) and the public branch endpoint (via ``RepoRef``),
    both of which answer anonymously, so this gate needs no GitHub token.
  * **Advanced setup, enforced by the fixed filename.** We look up runs of
    ``.github/workflows/codeql.yml``. CodeQL *default* setup commits no
    workflow file and runs under a dynamic workflow, so this lookup 404s for
    it; only *advanced* setup (a committed ``codeql.yml``) has runs here.
  * **strict_head.** A green run alone is not enough: a learner could go green
    once and then break the workflow on a later commit. We require the latest
    run's ``head_sha`` to equal the current ``main`` HEAD sha, so we verify the
    code sitting on ``main`` right now.
  * **Findings are fine.** ``conclusion == "success"`` means the CodeQL
    workflow completed; CodeQL alerts do not fail the run by default. We verify
    that scanning works, not that the code is vulnerability-free.

The language (Python) and workflow *quality* are judged by the LLM rubric step
from the committed ``codeql.yml`` content, not here.

URL validation and ownership checks are handled by the engine gate before this
module is called. For the workflow-runs seam see ``workflow_runs.py``; for the
branch-head seam see ``repo_ref.py``.
"""

from __future__ import annotations

import httpx
from opentelemetry import trace

from learn_to_cloud_shared.schemas import ValidationResult
from learn_to_cloud_shared.verification.errors import github_error_to_result
from learn_to_cloud_shared.verification.github_http import (
    RETRIABLE_EXCEPTIONS,
)
from learn_to_cloud_shared.verification.repo_ref import RepoRef, default_repo_ref
from learn_to_cloud_shared.verification.workflow_runs import (
    WorkflowRuns,
    default_workflow_runs,
)

# The committed workflow filename CodeQL advanced setup creates.
CODEQL_WORKFLOW_FILE = "codeql.yml"


async def verify_codeql_status(
    owner: str,
    repo: str,
    runs: WorkflowRuns | None = None,
    ref: RepoRef | None = None,
) -> ValidationResult:
    """Verify CodeQL is green on the current ``main`` HEAD of the learner's fork.

    URL validation and ownership checks are handled by the engine gate before
    this function is called.

    Args:
        owner: Repository owner (GitHub username).
        repo: Repository name.
        runs: Workflow-runs port (defaults to the production adapter).
        ref: Branch-head port (defaults to the production adapter).

    Returns:
        ``ValidationResult`` — valid when the latest ``codeql.yml`` run on
        ``main`` is ``success`` and its ``head_sha`` equals the current
        ``main`` HEAD.
    """
    runs = runs or default_workflow_runs()
    ref = ref or default_repo_ref()
    span = trace.get_current_span()
    try:
        latest_run = await runs.latest_run(owner, repo, CODEQL_WORKFLOW_FILE)
    except (httpx.HTTPStatusError, *RETRIABLE_EXCEPTIONS) as e:
        if isinstance(e, httpx.HTTPStatusError) and e.response.status_code == 404:
            span.set_attribute("http.response.status_code", 404)
            span.add_event("codeql.workflow_not_found")
            return ValidationResult(
                is_valid=False,
                message=(
                    f"No CodeQL workflow found in {owner}/{repo}. "
                    "Enable CodeQL 'advanced setup' and commit the workflow "
                    "as .github/workflows/codeql.yml, and make sure GitHub "
                    "Actions is enabled on your fork."
                ),
            )
        return github_error_to_result(
            e,
            event="codeql_status.api_error",
        )

    if latest_run is None:
        span.add_event("codeql.no_runs")
        return ValidationResult(
            is_valid=False,
            message=(
                "No CodeQL runs found on the main branch. "
                "Push a commit to main (or run the workflow) to trigger "
                "CodeQL, then try again."
            ),
        )

    status = latest_run.get("status")
    conclusion = latest_run.get("conclusion")
    run_head_sha = latest_run.get("head_sha")
    run_url = latest_run.get("html_url", "")
    run_number = latest_run.get("run_number", 0)

    if status != "completed":
        span.add_event("codeql.still_running")
        return ValidationResult(
            is_valid=False,
            message=(
                f"CodeQL run #{run_number} is still {status}. "
                "Wait for it to finish, then try again."
            ),
        )

    if conclusion != "success":
        span.add_event("codeql.failed")
        return ValidationResult(
            is_valid=False,
            message=(
                f"CodeQL run #{run_number} finished with "
                f"conclusion '{conclusion}'. "
                f"Check the run details at {run_url} "
                "to see what went wrong, fix it, and push to main."
            ),
        )

    try:
        head_sha = await ref.head_sha(owner, repo)
    except (httpx.HTTPStatusError, *RETRIABLE_EXCEPTIONS) as e:
        if isinstance(e, httpx.HTTPStatusError) and e.response.status_code == 404:
            span.set_attribute("http.response.status_code", 404)
            span.add_event("codeql.branch_not_found")
            return ValidationResult(
                is_valid=False,
                message=(
                    f"Could not find the main branch of {owner}/{repo}. "
                    "Make sure the repository is public and has a main branch."
                ),
            )
        return github_error_to_result(
            e,
            event="codeql_status.api_error",
        )

    if not head_sha:
        span.add_event("codeql.no_head_sha")
        return ValidationResult(
            is_valid=False,
            message=(
                "Could not determine the latest commit on your main branch. "
                "Make sure the repository is public and try again."
            ),
        )

    if run_head_sha != head_sha:
        span.add_event("codeql.head_not_scanned")
        return ValidationResult(
            is_valid=False,
            message=(
                "CodeQL passed, but not on your latest commit. Your most "
                "recent commit on main has not finished scanning yet. "
                "CodeQL runs a few minutes after you push; wait for the run "
                "on your latest commit, then try again."
            ),
        )

    span.add_event("codeql.passed")
    return ValidationResult(
        is_valid=True,
        message=(
            f"CodeQL is passing on main (run #{run_number}) for your latest "
            "commit. Security scanning is verified!"
        ),
    )
