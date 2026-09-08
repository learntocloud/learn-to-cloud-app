"""Adapter contracts independent of workflow execution."""

import sys
from unittest.mock import AsyncMock, Mock
from uuid import uuid4

import pytest
from learn_to_cloud_shared_test_support.requirement_factories import make_requirement

from learn_to_cloud_shared.models import SubmissionType
from learn_to_cloud_shared.schemas import TaskResult, ValidationResult
from learn_to_cloud_shared.submission_values import submitted_value_from_raw
from learn_to_cloud_shared.verification.checks import career as career_checks
from learn_to_cloud_shared.verification.checks import (
    deployed_api as deployed_api_checks,
)
from learn_to_cloud_shared.verification.checks import (
    deployment_architecture as deployment_architecture_checks,
)
from learn_to_cloud_shared.verification.checks import devops as devops_checks
from learn_to_cloud_shared.verification.checks import github as github_checks
from learn_to_cloud_shared.verification.checks import rubric as rubric_checks
from learn_to_cloud_shared.verification.checks import security as security_checks
from learn_to_cloud_shared.verification.checks import tokens as tokens_checks
from learn_to_cloud_shared.verification.checks.registry import CHECK_REGISTRY
from learn_to_cloud_shared.verification.core import StepContext, StepResult
from learn_to_cloud_shared.verification.evidence import EvidenceError
from learn_to_cloud_shared.verification.tasks.phase4 import (
    DEPLOYMENT_ARCHITECTURE_RUBRIC_TASK,
)
from learn_to_cloud_shared.verification.tasks.phase6 import (
    SECURITY_SCANNING_RUBRIC_TASK,
)
from learn_to_cloud_shared.verification_workflow import PreparedVerificationAttempt
from tests.fakes.repo_files import InMemoryRepoFiles


def _context(submission_type):
    requirement = make_requirement(submission_type)
    raw_value = (
        "https://api.example.com"
        if submission_type is SubmissionType.DEPLOYED_API
        else "https://github.com/learner/test-repo"
    )
    value = submitted_value_from_raw(requirement, raw_value)
    job = PreparedVerificationAttempt(
        id=uuid4(),
        user_id=1,
        github_username="learner",
        requirement=requirement,
        submitted_value=value,
    )
    return StepContext(
        job=job,
        repository=job.target,
        submitted_value=value,
        repo_files=InMemoryRepoFiles(),
    )


@pytest.mark.parametrize(
    ("params", "submission_type", "validator", "is_async"),
    [
        (
            github_checks.CIStatusParams(),
            SubmissionType.JOURNAL_API_VERIFIER,
            "verify_ci_status",
            True,
        ),
        (
            github_checks.ProfileReadmeCheckParams(),
            SubmissionType.PROFILE_README,
            "validate_profile_readme",
            True,
        ),
        (
            github_checks.RepoForkCheckParams(),
            SubmissionType.REPO_FORK,
            "validate_repo_fork",
            True,
        ),
        (
            tokens_checks.CtfTokenCheckParams(),
            SubmissionType.CTF_TOKEN,
            "verify_ctf_token",
            False,
        ),
        (
            tokens_checks.NetworkingTokenCheckParams(),
            SubmissionType.NETWORKING_TOKEN,
            "verify_networking_token",
            False,
        ),
        (
            deployed_api_checks.DeployedApiCheckParams(),
            SubmissionType.DEPLOYED_API,
            "validate_deployed_api",
            True,
        ),
        (
            deployment_architecture_checks.DeploymentArchitectureGateParams(),
            SubmissionType.DEPLOYMENT_ARCHITECTURE,
            "validate_deployment_architecture",
            True,
        ),
        (
            devops_checks.DevopsRequiredFilesParams(),
            SubmissionType.DEVOPS_ANALYSIS,
            "verify_required_devops_files",
            True,
        ),
        (
            devops_checks.PublicGhcrImageParams(),
            SubmissionType.DEVOPS_ANALYSIS,
            "verify_public_ghcr_image",
            True,
        ),
        (
            security_checks.CodeQLStatusParams(),
            SubmissionType.SECURITY_SCANNING,
            "verify_codeql_status",
            True,
        ),
        (
            career_checks.CareerReflectionGateParams(),
            SubmissionType.CAREER_REFLECTION,
            "validate_career_reflection",
            False,
        ),
    ],
)
@pytest.mark.parametrize(
    ("passed", "completed"), [(True, True), (False, True), (False, False)]
)
async def test_deterministic_results_preserve_identity_and_arguments(
    monkeypatch, params, submission_type, validator, is_async, passed, completed
):
    context = _context(submission_type)
    target = context.repository
    result = ValidationResult(
        is_valid=passed,
        verification_completed=completed,
        message="Authoritative feedback",
        username_match=False,
        repo_exists=True,
        cloud_provider="azure",
        error_code="evidence.configuration",
        task_results=[
            TaskResult(task_name="Original", passed=passed, feedback="Details")
        ],
    )
    mock = (AsyncMock if is_async else Mock)(return_value=result)
    monkeypatch.setattr(sys.modules[type(params).__module__], validator, mock)

    step_result = await CHECK_REGISTRY.check_for(params)(context, params)

    assert step_result.validation_result is result
    assert step_result.passed is passed
    assert step_result.stop_on_fail is True
    assert step_result.evidence == []
    assert step_result.grading_task is None
    if validator in {"validate_profile_readme", "validate_repo_fork"}:
        expected = (target,)
    elif validator in {"verify_ctf_token", "verify_networking_token"}:
        expected = (context.submitted_value.token, "learner")
    elif validator == "validate_deployed_api":
        expected = (context.submitted_value.url,)
    elif validator == "validate_career_reflection":
        expected = (context.submitted_value.text,)
    elif validator == "validate_deployment_architecture":
        expected = (
            context.job.requirement,
            context.submitted_value.text,
            target,
            context.repo_files,
        )
    elif validator == "verify_required_devops_files":
        expected = (target.owner, target.repo, context.repo_files)
    elif validator == "verify_public_ghcr_image":
        expected = (target.owner,)
    else:
        expected = (target.owner, target.repo)
    mock.assert_called_once_with(*expected)
    if is_async:
        mock.assert_awaited_once_with(*expected)


@pytest.mark.parametrize(
    "params",
    [
        github_checks.CIStatusParams(),
        devops_checks.DevopsRequiredFilesParams(),
        devops_checks.PublicGhcrImageParams(),
        security_checks.CodeQLStatusParams(),
        github_checks.ProfileReadmeCheckParams(),
        github_checks.RepoForkCheckParams(),
    ],
)
async def test_missing_target_preserves_completed_and_incomplete_results(params):
    context = _context(SubmissionType.CTF_TOKEN)
    result = await CHECK_REGISTRY.check_for(params)(context, params)
    completed = isinstance(
        params,
        (github_checks.ProfileReadmeCheckParams, github_checks.RepoForkCheckParams),
    )
    assert result == StepResult(
        passed=False,
        stop_on_fail=True,
        validation_result=ValidationResult(
            is_valid=False,
            message=(
                "Requirement configuration error: could not resolve GitHub target"
                if completed
                else "Requirement configuration error: missing required_repo"
            ),
            verification_completed=completed,
            error_code=None if completed else "evidence.configuration",
            username_match=True,
            repo_exists=False,
        ),
    )


@pytest.mark.parametrize(
    "params",
    [
        rubric_checks.LLMRubricReviewParams(
            task=SECURITY_SCANNING_RUBRIC_TASK, evidence_paths=("codeql.yml",)
        ),
        security_checks.SecurityScanningReviewParams(
            task=SECURITY_SCANNING_RUBRIC_TASK
        ),
        deployment_architecture_checks.DeploymentArchitectureReviewParams(
            task=DEPLOYMENT_ARCHITECTURE_RUBRIC_TASK
        ),
    ],
)
async def test_missing_rubric_target_raises_evidence_error(params):
    with pytest.raises(EvidenceError) as raised:
        await CHECK_REGISTRY.check_for(params)(
            _context(SubmissionType.CTF_TOKEN), params
        )
    assert raised.value.code == "evidence.configuration"


@pytest.mark.parametrize(("paths", "discover"), [((), False), (("codeql.yml",), True)])
def test_rubric_requires_exactly_one_evidence_mode(paths, discover):
    with pytest.raises(ValueError, match="Choose exactly one LLM evidence mode"):
        rubric_checks.LLMRubricReviewParams(
            task=SECURITY_SCANNING_RUBRIC_TASK,
            evidence_paths=paths,
            discover_paths=discover,
        )
