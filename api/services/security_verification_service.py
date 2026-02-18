"""Security scanning verification service.

This module provides Phase 6 verification: checking that learners have enabled
security scanning (Dependabot and/or CodeQL) on their GitHub repository.

Approach:
  1. Parse and validate the submitted GitHub URL
  2. Verify the repo owner matches the learner's GitHub username
  3. Fetch the repo file tree via GitHub API
  4. Check for Dependabot config and/or CodeQL workflow files
  5. If workflow files exist, fetch them to confirm CodeQL action usage
  6. Return per-check pass/fail results

No LLM is needed — verification is purely file-based.
"""

from __future__ import annotations

import asyncio
import logging

import httpx
from circuitbreaker import CircuitBreakerError, circuit
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential_jitter,
)

from schemas import TaskResult, ValidationResult
from services.devops_verification_service import _fetch_repo_tree
from services.github_hands_on_verification_service import (
    RETRIABLE_EXCEPTIONS,
    _get_github_client,
    _get_github_headers,
)
from services.llm_verification_base import VerificationError, validate_repo_url

logger = logging.getLogger(__name__)

# CodeQL action identifier in workflow file content
CODEQL_ACTION_PATTERN = "github/codeql-action"


class SecurityVerificationError(VerificationError):
    """Raised when Phase 6 security scanning verification fails."""


async def _check_dependabot(owner: str, repo: str, file_paths: list[str]) -> TaskResult:
    """Check for a valid Dependabot configuration file in the repo tree.

    Verifies both file existence and content: the file must contain
    a ``version`` key and at least one ``updates`` entry.
    """
    dependabot_paths = {".github/dependabot.yml", ".github/dependabot.yaml"}
    found = [p for p in file_paths if p in dependabot_paths]

    if not found:
        return TaskResult(
            task_name="Dependabot Configuration",
            passed=False,
            feedback=(
                "No Dependabot config found. Add a .github/dependabot.yml file "
                "to enable automated dependency updates."
            ),
        )

    content = await _fetch_workflow_content(owner, repo, found[0])
    if not content:
        return TaskResult(
            task_name="Dependabot Configuration",
            passed=False,
            feedback=(
                f"Found {found[0]} but could not read its content. "
                "Make sure the repository is public."
            ),
        )

    # Validate required keys exist in the file content
    has_version = "version" in content
    has_updates = "updates" in content

    if has_version and has_updates:
        return TaskResult(
            task_name="Dependabot Configuration",
            passed=True,
            feedback=f"Found valid Dependabot config: {found[0]}",
        )

    missing = []
    if not has_version:
        missing.append("version")
    if not has_updates:
        missing.append("updates")

    return TaskResult(
        task_name="Dependabot Configuration",
        passed=False,
        feedback=(
            f"Found {found[0]} but it is missing required keys: "
            f"{', '.join(missing)}. A valid Dependabot config needs a "
            "'version' key and at least one 'updates' entry."
        ),
    )


def _find_codeql_workflow_candidates(file_paths: list[str]) -> list[str]:
    """Find workflow files that may contain CodeQL configuration.

    Returns workflow paths that either:
    - Have 'codeql' in the filename
    - Are any .yml/.yaml file in .github/workflows/ (to check content)
    """
    codeql_by_name: list[str] = []
    other_workflows: list[str] = []

    for path in file_paths:
        if not path.startswith(".github/workflows/"):
            continue
        if not (path.endswith(".yml") or path.endswith(".yaml")):
            continue

        filename = path.rsplit("/", 1)[-1].lower()
        if "codeql" in filename:
            codeql_by_name.append(path)
        else:
            other_workflows.append(path)

    # Prioritise files with codeql in name, then check others
    return codeql_by_name + other_workflows


async def _fetch_workflow_content(owner: str, repo: str, path: str) -> str | None:
    """Fetch a single workflow file's raw content from GitHub."""
    client = await _get_github_client()
    headers = _get_github_headers()

    url = f"https://raw.githubusercontent.com/{owner}/{repo}/main/{path}"
    try:
        response = await client.get(url, headers=headers)
        response.raise_for_status()
        return response.text
    except httpx.HTTPStatusError:
        logger.warning(
            "security_scanning.workflow_fetch_failed",
            extra={"owner": owner, "repo": repo, "path": path},
        )
        return None


async def _check_codeql(owner: str, repo: str, file_paths: list[str]) -> TaskResult:
    """Check for CodeQL workflow in the repository.

    First checks filenames for 'codeql', then fetches workflow content
    to look for the github/codeql-action action reference.
    """
    candidates = _find_codeql_workflow_candidates(file_paths)

    if not candidates:
        return TaskResult(
            task_name="CodeQL Scanning",
            passed=False,
            feedback=(
                "No CodeQL workflow found. Add a CodeQL analysis workflow "
                "in .github/workflows/ using the github/codeql-action action."
            ),
        )

    # Check files with 'codeql' in the name first — they're most likely matches
    codeql_named = [c for c in candidates if "codeql" in c.rsplit("/", 1)[-1].lower()]
    if codeql_named:
        # Fetch to confirm it actually uses the CodeQL action
        content = await _fetch_workflow_content(owner, repo, codeql_named[0])
        if content and CODEQL_ACTION_PATTERN in content:
            return TaskResult(
                task_name="CodeQL Scanning",
                passed=True,
                feedback=f"Found CodeQL workflow: {codeql_named[0]}",
            )

    # Check remaining workflow files for CodeQL action usage
    # Limit to 5 files to avoid excessive API calls
    to_check = [c for c in candidates if c not in codeql_named][:5]

    fetch_tasks = [_fetch_workflow_content(owner, repo, path) for path in to_check]
    results = await asyncio.gather(*fetch_tasks, return_exceptions=True)

    for path, result in zip(to_check, results):
        if isinstance(result, BaseException) or result is None:
            continue
        if CODEQL_ACTION_PATTERN in result:
            return TaskResult(
                task_name="CodeQL Scanning",
                passed=True,
                feedback=f"Found CodeQL action in workflow: {path}",
            )

    return TaskResult(
        task_name="CodeQL Scanning",
        passed=False,
        feedback=(
            "No workflow using github/codeql-action found. Add a CodeQL "
            "analysis workflow to enable code scanning."
        ),
    )


@circuit(
    failure_threshold=5,
    recovery_timeout=60,
    expected_exception=RETRIABLE_EXCEPTIONS,
    name="security_scanning_circuit",
)
@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential_jitter(initial=0.5, max=10),
    retry=retry_if_exception_type(RETRIABLE_EXCEPTIONS),
    reraise=True,
)
async def _verify_security_scanning(
    owner: str, repo: str, file_paths: list[str]
) -> ValidationResult:
    """Internal: run security scanning checks with circuit breaker + retry."""
    dependabot_result = await _check_dependabot(owner, repo, file_paths)
    codeql_result = await _check_codeql(owner, repo, file_paths)

    task_results = [dependabot_result, codeql_result]
    any_passed = dependabot_result.passed or codeql_result.passed
    all_passed = dependabot_result.passed and codeql_result.passed

    passed_count = sum(1 for t in task_results if t.passed)

    logger.info(
        "security_scanning.checks_completed",
        extra={
            "owner": owner,
            "repo": repo,
            "dependabot": dependabot_result.passed,
            "codeql": codeql_result.passed,
            "passed": passed_count,
            "total": len(task_results),
        },
    )

    if all_passed:
        message = (
            "Both Dependabot and CodeQL scanning are configured. "
            "Your repository has comprehensive security scanning enabled."
        )
    elif any_passed:
        passed_name = (
            dependabot_result.task_name
            if dependabot_result.passed
            else codeql_result.task_name
        )
        message = (
            f"{passed_name} is configured — security scanning verified! "
            "Consider enabling the other scanner for more comprehensive coverage."
        )
    else:
        message = (
            "No security scanning found. Enable Dependabot "
            "(.github/dependabot.yml) or CodeQL (.github/workflows/) "
            "on your repository and try again."
        )

    return ValidationResult(
        is_valid=any_passed,
        message=message,
        task_results=task_results,
    )


async def validate_security_scanning(
    repo_url: str, github_username: str
) -> ValidationResult:
    """Verify a learner's GitHub repo has security scanning enabled.

    This is the main entry point for Phase 6 security scanning verification.

    Flow:
      1. Parse and validate the GitHub URL
      2. Verify repo owner matches the learner's GitHub username
      3. Fetch the repo file tree
      4. Check for Dependabot config and/or CodeQL workflows
      5. Return per-check results (pass if at least one is found)

    Args:
        repo_url: URL of the learner's repository.
        github_username: The learner's GitHub username (for ownership validation).

    Returns:
        ValidationResult with is_valid=True if at least one security feature
        is found, and detailed task_results for feedback.
    """
    result = validate_repo_url(repo_url, github_username)
    if isinstance(result, ValidationResult):
        return result
    owner, repo = result

    try:
        try:
            all_files = await _fetch_repo_tree(owner, repo)
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                return ValidationResult(
                    is_valid=False,
                    message=(
                        f"Repository '{owner}/{repo}' not found. "
                        "Make sure the repository is public."
                    ),
                    username_match=True,
                )
            raise

        return await _verify_security_scanning(owner, repo, all_files)

    except CircuitBreakerError:
        logger.error(
            "security_scanning.circuit_open",
            extra={
                "owner": owner,
                "repo": repo,
                "github_username": github_username,
            },
        )
        return ValidationResult(
            is_valid=False,
            message=(
                "Security scanning verification is temporarily unavailable. "
                "Please try again in a few minutes."
            ),
            server_error=True,
        )
    except SecurityVerificationError as e:
        logger.exception(
            "security_scanning.failed",
            extra={
                "owner": owner,
                "repo": repo,
                "retriable": e.retriable,
                "github_username": github_username,
            },
        )
        return ValidationResult(
            is_valid=False,
            message=f"Security scanning verification failed: {e}",
            server_error=e.retriable,
        )
    except RETRIABLE_EXCEPTIONS:
        logger.exception(
            "security_scanning.request_error",
            extra={
                "owner": owner,
                "repo": repo,
                "github_username": github_username,
            },
        )
        return ValidationResult(
            is_valid=False,
            message="Unable to reach GitHub. Please try again later.",
            server_error=True,
        )
