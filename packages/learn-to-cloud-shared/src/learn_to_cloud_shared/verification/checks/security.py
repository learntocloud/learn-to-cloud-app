"""Typed security checks for verification workflows."""

from __future__ import annotations

import httpx

from learn_to_cloud_shared.verification.checks.common import (
    missing_repository_result,
    validation_step_result,
)
from learn_to_cloud_shared.verification.codeql_status import verify_codeql_status
from learn_to_cloud_shared.verification.core import StepContext, StepResult
from learn_to_cloud_shared.verification.evidence import EvidenceError
from learn_to_cloud_shared.verification.github_errors import (
    GitHubServerError,
    github_error_to_result,
)
from learn_to_cloud_shared.verification.repo_files import default_repo_files
from learn_to_cloud_shared.verification.security_scanning import (
    collect_security_scanning_evidence,
)
from learn_to_cloud_shared.verification.tasks.base import VerificationTask


async def check_codeql_status(context: StepContext) -> StepResult:
    """Deterministic Phase 6 gate: CodeQL green on the fork's current main HEAD."""
    target = context.repository
    if target is None:
        return missing_repository_result()
    result = await verify_codeql_status(target.owner, target.repo)
    return validation_step_result(result)


async def check_security_scanning_review(
    context: StepContext,
    *,
    task: VerificationTask,
) -> StepResult:
    """Bundle the fork's security-scanning config files for rubric grading."""
    target = context.repository
    if target is None:
        raise EvidenceError("evidence.configuration")
    repo_files = context.repo_files or default_repo_files()
    try:
        bundle = await collect_security_scanning_evidence(
            target.owner,
            target.repo,
            task,
            repo_files=repo_files,
        )
    except (GitHubServerError, httpx.HTTPStatusError, httpx.RequestError) as exc:
        return StepResult(
            passed=False,
            validation_result=github_error_to_result(
                exc, event="security_scanning.repo_file_error"
            ),
        )
    return StepResult(
        passed=True,
        evidence=[bundle],
        grading_task=task,
    )
