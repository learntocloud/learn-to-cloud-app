"""Adapter contracts independent of workflow execution."""

import sys
from functools import partial
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
from learn_to_cloud_shared.verification.checks import devops as devops_checks
from learn_to_cloud_shared.verification.checks import github as github_checks
from learn_to_cloud_shared.verification.checks import security as security_checks
from learn_to_cloud_shared.verification.checks import tokens as tokens_checks
from learn_to_cloud_shared.verification.core import StepContext, StepResult
from learn_to_cloud_shared.verification.evidence import EvidenceError
from learn_to_cloud_shared.verification.tasks.phase6 import (
    SECURITY_SCANNING_RUBRIC_TASK,
)
from learn_to_cloud_shared.verification.tasks.phase7 import (
    CAREER_REFLECTION_RUBRIC_TASK,
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
    ("check", "submission_type", "validator", "is_async"),
    [
        (
            github_checks.check_github_ci_passing,
            SubmissionType.JOURNAL_API_VERIFIER,
            "verify_ci_status",
            True,
        ),
        (
            github_checks.check_profile_readme,
            SubmissionType.PROFILE_README,
            "validate_profile_readme",
            True,
        ),
        (
            github_checks.check_repo_fork,
            SubmissionType.REPO_FORK,
            "validate_repo_fork",
            True,
        ),
        (
            tokens_checks.check_ctf_token,
            SubmissionType.CTF_TOKEN,
            "verify_ctf_token",
            False,
        ),
        (
            tokens_checks.check_networking_token,
            SubmissionType.NETWORKING_TOKEN,
            "verify_networking_token",
            False,
        ),
        (
            deployed_api_checks.check_deployed_api,
            SubmissionType.DEPLOYED_API,
            "validate_deployed_api",
            True,
        ),
        (
            devops_checks.check_devops_pipeline,
            SubmissionType.DEVOPS_ANALYSIS,
            "verify_devops_pipeline",
            True,
        ),
        (
            security_checks.check_codeql_status,
            SubmissionType.SECURITY_SCANNING,
            "verify_codeql_status",
            True,
        ),
    ],
)
@pytest.mark.parametrize(
    ("passed", "completed"), [(True, True), (False, True), (False, False)]
)
async def test_deterministic_results_preserve_identity_and_arguments(
    monkeypatch, check, submission_type, validator, is_async, passed, completed
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
    monkeypatch.setattr(sys.modules[check.__module__], validator, mock)

    step_result = await check(context)

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
    else:
        expected = (target.owner, target.repo)
    mock.assert_called_once_with(*expected)
    if is_async:
        mock.assert_awaited_once_with(*expected)


@pytest.mark.parametrize(
    ("passed", "completed"),
    [(True, True), (False, True), (False, False), (True, False)],
)
async def test_career_check_validates_before_preparing_grading(
    monkeypatch, passed, completed
):
    context = _context(SubmissionType.CAREER_REFLECTION)
    validation = ValidationResult(
        is_valid=passed,
        verification_completed=completed,
        message="Reflection feedback",
    )
    validate = Mock(return_value=validation)
    collect = Mock(wraps=career_checks.collect_career_reflection_evidence)
    monkeypatch.setattr(career_checks, "validate_career_reflection", validate)
    monkeypatch.setattr(career_checks, "collect_career_reflection_evidence", collect)

    result = await career_checks.check_career_reflection(
        context, task=CAREER_REFLECTION_RUBRIC_TASK
    )

    validate.assert_called_once_with(context.submitted_value.text)
    assert result.validation_result is validation
    assert result.passed is passed
    if passed and completed:
        collect.assert_called_once_with(
            context.submitted_value.text, CAREER_REFLECTION_RUBRIC_TASK
        )
        assert len(result.evidence) == 1
        assert result.evidence[0].task_id == CAREER_REFLECTION_RUBRIC_TASK.id
        assert result.evidence[0].items[0].content == context.submitted_value.text
        assert result.grading_task is CAREER_REFLECTION_RUBRIC_TASK
        assert not result.stop_on_fail
    else:
        collect.assert_not_called()
        assert result.evidence == []
        assert result.grading_task is None
        assert result.stop_on_fail


async def test_career_check_rejects_non_text_values():
    with pytest.raises(
        TypeError, match="Career reflection check requires a text value"
    ):
        await career_checks.check_career_reflection(
            _context(SubmissionType.CTF_TOKEN), task=CAREER_REFLECTION_RUBRIC_TASK
        )


@pytest.mark.parametrize(
    "check",
    [
        github_checks.check_github_ci_passing,
        devops_checks.check_devops_pipeline,
        security_checks.check_codeql_status,
        github_checks.check_profile_readme,
        github_checks.check_repo_fork,
    ],
)
async def test_missing_target_preserves_completed_and_incomplete_results(check):
    context = _context(SubmissionType.CTF_TOKEN)
    result = await check(context)
    completed = check in {
        github_checks.check_profile_readme,
        github_checks.check_repo_fork,
    }
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
    "check",
    [
        partial(
            security_checks.check_security_scanning_review,
            task=SECURITY_SCANNING_RUBRIC_TASK,
        ),
    ],
)
async def test_missing_rubric_target_raises_evidence_error(check):
    with pytest.raises(EvidenceError) as raised:
        await check(_context(SubmissionType.CTF_TOKEN))
    assert raised.value.code == "evidence.configuration"
