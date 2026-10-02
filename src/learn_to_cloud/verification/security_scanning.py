"""Phase 6 security scanning verification.

A deterministic gate (``codeql_status``) proves CodeQL ran green on the current
``main`` HEAD. Only then is the committed CodeQL workflow and any Dependabot
config collected for an LLM rubric review of its quality.
"""

from __future__ import annotations

import httpx2

from learn_to_cloud.verification.codeql_status import verify_codeql_status
from learn_to_cloud.verification.core import CheckResult, GradingEvidence
from learn_to_cloud.verification.evidence import collect_repo_file_evidence
from learn_to_cloud.verification.github_api import GitHub
from learn_to_cloud.verification.github_errors import (
    GitHubServerError,
    github_error_to_result,
)
from learn_to_cloud.verification.repository_target import GitHubRepositoryTarget
from learn_to_cloud.verification.tasks.base import (
    EvidenceBundle,
    VerificationTask,
)
from learn_to_cloud.verification.tasks.phase6 import (
    CODEQL_WORKFLOW_PATH,
    DEPENDABOT_CONFIG_PATHS,
    SECURITY_SCANNING_RUBRIC_TASK,
)

SECURITY_SCANNING_EVIDENCE_PATHS = [CODEQL_WORKFLOW_PATH, *DEPENDABOT_CONFIG_PATHS]


async def collect_security_scanning_evidence(
    owner: str,
    repo: str,
    github: GitHub,
    task: VerificationTask = SECURITY_SCANNING_RUBRIC_TASK,
) -> EvidenceBundle:
    """Collect bounded Phase 6 repository evidence for rubric grading.

    Fetches the fixed CodeQL workflow (``.github/workflows/codeql.yml``) and
    canonical optional Dependabot config from the default branch. Every selected
    file must fit in full; absent Dependabot is not a failed requirement.
    """
    return await collect_repo_file_evidence(
        github, owner, repo, SECURITY_SCANNING_EVIDENCE_PATHS, task
    )


async def verify_security_scanning(
    target: GitHubRepositoryTarget,
    github: GitHub,
    task: VerificationTask = SECURITY_SCANNING_RUBRIC_TASK,
) -> CheckResult:
    """Require CodeQL green on main, then bundle the scanning config for grading."""
    codeql = await verify_codeql_status(target.owner, target.repo, github)
    if not codeql.is_valid:
        return CheckResult(validation_result=codeql)
    try:
        bundle = await collect_security_scanning_evidence(
            target.owner, target.repo, github, task
        )
    except (GitHubServerError, httpx2.HTTPStatusError, httpx2.RequestError) as exc:
        return CheckResult(
            validation_result=github_error_to_result(
                exc, event="security_scanning.repo_file_error"
            )
        )
    return CheckResult(
        validation_result=codeql,
        grading=GradingEvidence(task=task, bundle=bundle),
    )
