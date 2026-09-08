"""Built-in verification workflows by submission type."""

from __future__ import annotations

from learn_to_cloud_shared.models import SubmissionType
from learn_to_cloud_shared.verification.checks.career import (
    CareerReflectionGateParams,
    CareerReflectionReviewParams,
)
from learn_to_cloud_shared.verification.checks.deployed_api import (
    DeployedApiCheckParams,
)
from learn_to_cloud_shared.verification.checks.deployment_architecture import (
    DeploymentArchitectureGateParams,
    DeploymentArchitectureReviewParams,
)
from learn_to_cloud_shared.verification.checks.devops import (
    DevopsRequiredFilesParams,
    PublicGhcrImageParams,
)
from learn_to_cloud_shared.verification.checks.github import (
    CIStatusParams,
    ProfileReadmeCheckParams,
    RepoForkCheckParams,
)
from learn_to_cloud_shared.verification.checks.rubric import LLMRubricReviewParams
from learn_to_cloud_shared.verification.checks.security import (
    CodeQLStatusParams,
    SecurityScanningReviewParams,
)
from learn_to_cloud_shared.verification.checks.tokens import (
    CtfTokenCheckParams,
    NetworkingTokenCheckParams,
)
from learn_to_cloud_shared.verification.core import Step, VerificationWorkflow
from learn_to_cloud_shared.verification.tasks.base import LLMRubricGraderConfig
from learn_to_cloud_shared.verification.tasks.phase4 import (
    DEPLOYMENT_ARCHITECTURE_RUBRIC_TASK,
)
from learn_to_cloud_shared.verification.tasks.phase5 import (
    DEVOPS_IMPLEMENTATION_RUBRIC_TASK,
)
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
            params=CIStatusParams(),
            task_id="journal-api-implementation-ci",
        ),
    ),
)

register_workflow(SubmissionType.JOURNAL_API_VERIFIER, _JOURNAL_API_WORKFLOW)


_DEPLOYMENT_ARCHITECTURE_RUBRIC = DEPLOYMENT_ARCHITECTURE_RUBRIC_TASK.grader
assert isinstance(_DEPLOYMENT_ARCHITECTURE_RUBRIC, LLMRubricGraderConfig)

_DEPLOYMENT_ARCHITECTURE_WORKFLOW = VerificationWorkflow(
    requires_username=True,
    steps=(
        Step(
            params=DeploymentArchitectureGateParams(),
            task_id="deployment-architecture-gate",
        ),
        Step(
            params=DeploymentArchitectureReviewParams(
                task=DEPLOYMENT_ARCHITECTURE_RUBRIC_TASK,
            ),
            task_id=DEPLOYMENT_ARCHITECTURE_RUBRIC_TASK.id,
        ),
    ),
    rubric=_DEPLOYMENT_ARCHITECTURE_RUBRIC,
)

register_workflow(
    SubmissionType.DEPLOYMENT_ARCHITECTURE, _DEPLOYMENT_ARCHITECTURE_WORKFLOW
)


_DEPLOYED_API_WORKFLOW = VerificationWorkflow(
    requires_username=False,
    steps=(
        Step(
            params=DeployedApiCheckParams(),
            task_id="deployed-api-check",
        ),
    ),
)

register_workflow(SubmissionType.DEPLOYED_API, _DEPLOYED_API_WORKFLOW)


_DEVOPS_IMPLEMENTATION_RUBRIC = DEVOPS_IMPLEMENTATION_RUBRIC_TASK.grader
assert isinstance(_DEVOPS_IMPLEMENTATION_RUBRIC, LLMRubricGraderConfig)

_DEVOPS_ANALYSIS_WORKFLOW = VerificationWorkflow(
    requires_username=True,
    steps=(
        Step(
            params=DevopsRequiredFilesParams(),
            task_id="devops-required-files",
        ),
        Step(
            params=PublicGhcrImageParams(),
            task_id="public-ghcr-image",
        ),
        Step(
            params=LLMRubricReviewParams(
                task=DEVOPS_IMPLEMENTATION_RUBRIC_TASK,
                discover_paths=True,
            ),
            task_id=DEVOPS_IMPLEMENTATION_RUBRIC_TASK.id,
        ),
    ),
    rubric=_DEVOPS_IMPLEMENTATION_RUBRIC,
)

register_workflow(SubmissionType.DEVOPS_ANALYSIS, _DEVOPS_ANALYSIS_WORKFLOW)


_SECURITY_SCANNING_RUBRIC = SECURITY_SCANNING_RUBRIC_TASK.grader
assert isinstance(_SECURITY_SCANNING_RUBRIC, LLMRubricGraderConfig)

_SECURITY_SCANNING_WORKFLOW = VerificationWorkflow(
    requires_username=True,
    steps=(
        Step(
            params=CodeQLStatusParams(),
            task_id="codeql-status-gate",
        ),
        Step(
            params=SecurityScanningReviewParams(task=SECURITY_SCANNING_RUBRIC_TASK),
            task_id=SECURITY_SCANNING_RUBRIC_TASK.id,
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
            params=CareerReflectionGateParams(),
            task_id="career-reflection-gate",
        ),
        Step(
            params=CareerReflectionReviewParams(task=CAREER_REFLECTION_RUBRIC_TASK),
            task_id=CAREER_REFLECTION_RUBRIC_TASK.id,
        ),
    ),
    rubric=_CAREER_REFLECTION_RUBRIC,
)

register_workflow(SubmissionType.CAREER_REFLECTION, _CAREER_REFLECTION_WORKFLOW)


_PROFILE_README_WORKFLOW = VerificationWorkflow(
    requires_username=True,
    steps=(
        Step(
            params=ProfileReadmeCheckParams(),
            task_id="profile-readme-check",
        ),
    ),
)

register_workflow(SubmissionType.PROFILE_README, _PROFILE_README_WORKFLOW)


_REPO_FORK_WORKFLOW = VerificationWorkflow(
    requires_username=True,
    steps=(
        Step(
            params=RepoForkCheckParams(),
            task_id="repo-fork-check",
        ),
    ),
)

register_workflow(SubmissionType.REPO_FORK, _REPO_FORK_WORKFLOW)


_CTF_TOKEN_WORKFLOW = VerificationWorkflow(
    requires_username=True,
    steps=(
        Step(
            params=CtfTokenCheckParams(),
            task_id="ctf-token-check",
        ),
    ),
)

register_workflow(SubmissionType.CTF_TOKEN, _CTF_TOKEN_WORKFLOW)


_NETWORKING_TOKEN_WORKFLOW = VerificationWorkflow(
    requires_username=True,
    steps=(
        Step(
            params=NetworkingTokenCheckParams(),
            task_id="networking-token-check",
        ),
    ),
)

register_workflow(SubmissionType.NETWORKING_TOKEN, _NETWORKING_TOKEN_WORKFLOW)
