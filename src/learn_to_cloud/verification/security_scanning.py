"""Phase 6 verification: CodeQL scanning plus a live HTTPS-only check.

CodeQL must be green on the current ``main`` HEAD, and the production API must
refuse plain HTTP and send HSTS.
"""

from __future__ import annotations

from learn_to_cloud.schemas.verification import TaskResult, ValidationResult
from learn_to_cloud.verification.codeql_status import verify_codeql_status
from learn_to_cloud.verification.github_api import GitHub
from learn_to_cloud.verification.repository_target import GitHubRepositoryTarget
from learn_to_cloud.verification.secure_deployment import verify_secure_deployment


async def verify_security_scanning(
    target: GitHubRepositoryTarget,
    github: GitHub,
) -> ValidationResult:
    """Require CodeQL green on ``main`` and a locked-down live API."""
    codeql = await verify_codeql_status(target.owner, target.repo, github)
    if not codeql.is_valid:
        return codeql
    live = await verify_secure_deployment(target.owner, target.repo, github)
    task_results = [
        TaskResult(task_name="codeql", passed=True, feedback=codeql.message),
        *(live.task_results or []),
    ]
    if not live.is_valid:
        return live.model_copy(update={"task_results": task_results})
    return ValidationResult(
        is_valid=True,
        message=f"{codeql.message} {live.message}",
        task_results=task_results,
    )
