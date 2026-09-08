"""Built-in verification workflows by submission type."""

from __future__ import annotations

from functools import partial

from learn_to_cloud_shared.models import SubmissionType
from learn_to_cloud_shared.verification.checks.career import (
    check_career_reflection,
)
from learn_to_cloud_shared.verification.checks.deployed_api import (
    check_deployed_api,
)
from learn_to_cloud_shared.verification.checks.devops import (
    check_devops_pipeline,
)
from learn_to_cloud_shared.verification.checks.github import (
    check_github_ci_passing,
    check_profile_readme,
    check_repo_fork,
)
from learn_to_cloud_shared.verification.checks.security import (
    check_codeql_status,
    check_security_scanning_review,
)
from learn_to_cloud_shared.verification.checks.tokens import (
    check_ctf_token,
    check_networking_token,
)
from learn_to_cloud_shared.verification.core import Step, VerificationWorkflow
from learn_to_cloud_shared.verification.tasks.base import LLMRubricGraderConfig
from learn_to_cloud_shared.verification.tasks.phase6 import (
    SECURITY_SCANNING_RUBRIC_TASK,
)
from learn_to_cloud_shared.verification.tasks.phase7 import (
    CAREER_REFLECTION_RUBRIC_TASK,
)

_WORKFLOW_REGISTRY: dict[SubmissionType, VerificationWorkflow] = {}


def register_workflow(
    submission_type: SubmissionType, workflow: VerificationWorkflow
) -> None:
    """Register a workflow for a submission type (raises on dupes)."""
    if submission_type in _WORKFLOW_REGISTRY:
        raise ValueError(f"Workflow already registered: {submission_type}")
    _WORKFLOW_REGISTRY[submission_type] = workflow


def workflow_for(submission_type: SubmissionType) -> VerificationWorkflow | None:
    """Return the workflow for a submission type, if any."""
    return _WORKFLOW_REGISTRY.get(submission_type)


_JOURNAL_API_WORKFLOW = VerificationWorkflow(
    requires_username=True,
    steps=(
        Step(
            name="github_ci_passing",
            task_id="journal-api-implementation-ci",
            check=check_github_ci_passing,
        ),
    ),
)

register_workflow(SubmissionType.JOURNAL_API_VERIFIER, _JOURNAL_API_WORKFLOW)


_DEPLOYED_API_WORKFLOW = VerificationWorkflow(
    requires_username=False,
    steps=(
        Step(
            name="deployed_api_check",
            task_id="deployed-api-check",
            check=check_deployed_api,
        ),
    ),
)

register_workflow(SubmissionType.DEPLOYED_API, _DEPLOYED_API_WORKFLOW)


_DEVOPS_ANALYSIS_WORKFLOW = VerificationWorkflow(
    requires_username=True,
    steps=(
        Step(
            name="devops_pipeline",
            task_id="devops-pipeline",
            check=check_devops_pipeline,
        ),
    ),
)

register_workflow(SubmissionType.DEVOPS_ANALYSIS, _DEVOPS_ANALYSIS_WORKFLOW)


_SECURITY_SCANNING_RUBRIC = SECURITY_SCANNING_RUBRIC_TASK.grader
assert isinstance(_SECURITY_SCANNING_RUBRIC, LLMRubricGraderConfig)

_SECURITY_SCANNING_WORKFLOW = VerificationWorkflow(
    requires_username=True,
    steps=(
        Step(
            name="codeql_status",
            task_id="codeql-status-gate",
            check=check_codeql_status,
        ),
        Step(
            name="security_scanning_review",
            task_id=SECURITY_SCANNING_RUBRIC_TASK.id,
            check=partial(
                check_security_scanning_review, task=SECURITY_SCANNING_RUBRIC_TASK
            ),
        ),
    ),
    rubric=_SECURITY_SCANNING_RUBRIC,
)

register_workflow(SubmissionType.SECURITY_SCANNING, _SECURITY_SCANNING_WORKFLOW)


_CAREER_REFLECTION_RUBRIC = CAREER_REFLECTION_RUBRIC_TASK.grader
assert isinstance(_CAREER_REFLECTION_RUBRIC, LLMRubricGraderConfig)

_CAREER_REFLECTION_WORKFLOW = VerificationWorkflow(
    requires_username=False,
    steps=(
        Step(
            name="career_reflection",
            task_id=CAREER_REFLECTION_RUBRIC_TASK.id,
            check=partial(check_career_reflection, task=CAREER_REFLECTION_RUBRIC_TASK),
        ),
    ),
    rubric=_CAREER_REFLECTION_RUBRIC,
)

register_workflow(SubmissionType.CAREER_REFLECTION, _CAREER_REFLECTION_WORKFLOW)


_PROFILE_README_WORKFLOW = VerificationWorkflow(
    requires_username=True,
    steps=(
        Step(
            name="profile_readme_check",
            task_id="profile-readme-check",
            check=check_profile_readme,
        ),
    ),
)

register_workflow(SubmissionType.PROFILE_README, _PROFILE_README_WORKFLOW)


_REPO_FORK_WORKFLOW = VerificationWorkflow(
    requires_username=True,
    steps=(
        Step(
            name="repo_fork_check",
            task_id="repo-fork-check",
            check=check_repo_fork,
        ),
    ),
)

register_workflow(SubmissionType.REPO_FORK, _REPO_FORK_WORKFLOW)


_CTF_TOKEN_WORKFLOW = VerificationWorkflow(
    requires_username=True,
    steps=(
        Step(
            name="ctf_token_check",
            task_id="ctf-token-check",
            check=check_ctf_token,
        ),
    ),
)

register_workflow(SubmissionType.CTF_TOKEN, _CTF_TOKEN_WORKFLOW)


_NETWORKING_TOKEN_WORKFLOW = VerificationWorkflow(
    requires_username=True,
    steps=(
        Step(
            name="networking_token_check",
            task_id="networking-token-check",
            check=check_networking_token,
        ),
    ),
)

register_workflow(SubmissionType.NETWORKING_TOKEN, _NETWORKING_TOKEN_WORKFLOW)
