"""Per-type dispatch and verifier contracts, independent of ownership and tracing."""

from unittest.mock import AsyncMock, Mock
from uuid import uuid4

import pytest

from learn_to_cloud.models import SubmissionType
from learn_to_cloud.schemas.verification import TaskResult, ValidationResult
from learn_to_cloud.verification import engine as engine_module
from learn_to_cloud.verification import security_scanning
from learn_to_cloud.verification.attempt_types import PreparedVerificationAttempt
from learn_to_cloud.verification.core import CheckResult
from learn_to_cloud.verification.evidence import EvidenceError
from learn_to_cloud.verification.repository_ownership import OwnedRepository
from learn_to_cloud.verification.submission_values import (
    DeployedUrlValue,
    TextValue,
    TokenValue,
    submitted_value_from_raw,
)
from learn_to_cloud.verification.tasks.phase7 import CAREER_REFLECTION_RUBRIC_TASK
from tests.support.fakes.github import FakeGitHub
from tests.support.requirement_factories import make_requirement

_REPOSITORY_TYPES = [
    SubmissionType.PROFILE_README,
    SubmissionType.REPO_FORK,
    SubmissionType.JOURNAL_API_VERIFIER,
    SubmissionType.DEVOPS_VERIFICATION,
    SubmissionType.SECURITY_SCANNING,
]


def _job(submission_type, raw_value=None) -> PreparedVerificationAttempt:
    requirement = make_requirement(submission_type)
    if raw_value is None:
        raw_value = (
            "https://api.example.com"
            if submission_type is SubmissionType.DEPLOYED_API
            else "https://github.com/learner/test-repo"
        )
    return PreparedVerificationAttempt(
        id=uuid4(),
        user_id=1,
        github_username="learner",
        requirement=requirement,
        submitted_value=submitted_value_from_raw(requirement, raw_value),
    )


def _owned(job, parent=None) -> OwnedRepository | None:
    target = job.target
    return None if target is None else OwnedRepository(target=target, parent=parent)


@pytest.mark.parametrize(
    ("submission_type", "verifier", "is_async"),
    [
        (SubmissionType.JOURNAL_API_VERIFIER, "verify_ci_status", True),
        (SubmissionType.CTF_TOKEN, "verify_ctf_token", False),
        (SubmissionType.NETWORKING_TOKEN, "verify_networking_token", False),
        (SubmissionType.DEPLOYED_API, "validate_deployed_api", True),
        (SubmissionType.DEVOPS_VERIFICATION, "verify_devops_pipeline", True),
    ],
)
@pytest.mark.parametrize(
    ("passed", "completed"), [(True, True), (False, True), (False, False)]
)
async def test_dispatch_passes_typed_inputs_and_preserves_result(
    monkeypatch, submission_type, verifier, is_async, passed, completed
):
    job = _job(submission_type)
    repository = _owned(job)
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
    monkeypatch.setattr(engine_module, verifier, mock)
    github = FakeGitHub()

    check_result = await engine_module._dispatch(job, repository, github)

    assert check_result.validation_result is result
    assert check_result.grading is None
    match job.submitted_value:
        case TokenValue(token=token):
            expected = (token, "learner")
        case DeployedUrlValue(url=url):
            expected = (url,)
        case _:
            assert repository is not None
            expected = (repository.target.owner, repository.target.repo, github)
    mock.assert_called_once_with(*expected)
    if is_async:
        mock.assert_awaited_once_with(*expected)


async def test_profile_readme_passes_from_ownership_alone():
    job = _job(SubmissionType.PROFILE_README)
    result = await engine_module._dispatch(job, _owned(job), FakeGitHub())
    assert result.validation_result.is_valid
    assert result.validation_result.repo_exists


@pytest.mark.parametrize("parent", ["owner/test-repo", "elsewhere/test-repo", None])
async def test_repo_fork_uses_parent_from_ownership_metadata(parent):
    job = _job(SubmissionType.REPO_FORK)
    assert job.target is not None
    result = await engine_module._dispatch(job, _owned(job, parent), FakeGitHub())
    assert result.validation_result.is_valid is (parent == job.target.forked_from)


@pytest.mark.parametrize("submission_type", _REPOSITORY_TYPES)
async def test_repository_types_never_run_without_ownership(submission_type):
    with pytest.raises(ValueError, match="ownership-verified target"):
        await engine_module._dispatch(_job(submission_type), None, FakeGitHub())


async def test_mismatched_submitted_value_is_a_programming_error():
    job = _job(SubmissionType.CAREER_REFLECTION, "Reflection")
    mismatched = PreparedVerificationAttempt(
        id=job.id,
        user_id=job.user_id,
        github_username=job.github_username,
        requirement=make_requirement(SubmissionType.CTF_TOKEN),
        submitted_value=job.submitted_value,
    )
    with pytest.raises(TypeError, match="requires TokenValue"):
        await engine_module._dispatch(mismatched, None, FakeGitHub())


@pytest.mark.parametrize("text", ["", "   ", "\n\t"])
def test_career_text_rejects_blank_input_before_verification(text):
    with pytest.raises(ValueError, match="canonical text"):
        TextValue(text)
    with pytest.raises(ValueError, match="cannot be empty"):
        submitted_value_from_raw(
            make_requirement(SubmissionType.CAREER_REFLECTION), text
        )


async def test_career_reflection_rejects_evidence_exceeding_byte_limit():
    task = CAREER_REFLECTION_RUBRIC_TASK
    text = "🦊" * (task.evidence.max_file_size_bytes // 4 + 1)

    with pytest.raises(EvidenceError, match="evidence.item_limit"):
        await engine_module._dispatch(
            _job(SubmissionType.CAREER_REFLECTION, text), None, FakeGitHub()
        )


async def test_dispatch_wraps_security_scanning_result(monkeypatch):
    job = _job(SubmissionType.SECURITY_SCANNING)
    repository = _owned(job)
    assert repository is not None
    result = ValidationResult(is_valid=True, message="Secure.")
    verify = AsyncMock(return_value=result)
    monkeypatch.setattr(engine_module, "verify_security_scanning", verify)
    github = FakeGitHub()

    check_result = await engine_module._dispatch(job, repository, github)

    assert check_result == CheckResult(validation_result=result)
    verify.assert_awaited_once_with(repository.target, github)


@pytest.mark.parametrize("completed", [True, False])
async def test_security_codeql_failure_skips_live_check(monkeypatch, completed):
    target = _job(SubmissionType.SECURITY_SCANNING).target
    assert target is not None
    gate = ValidationResult(
        is_valid=False,
        verification_completed=completed,
        message="No CodeQL runs found",
    )
    verify = AsyncMock(return_value=gate)
    monkeypatch.setattr(security_scanning, "verify_codeql_status", verify)
    live = AsyncMock()
    monkeypatch.setattr(security_scanning, "verify_secure_deployment", live)

    github = FakeGitHub()
    result = await security_scanning.verify_security_scanning(target, github)

    assert result is gate
    verify.assert_awaited_once_with(target.owner, target.repo, github)
    live.assert_not_awaited()


def _security_gates(monkeypatch, live: ValidationResult):
    gate = ValidationResult(is_valid=True, message="CodeQL green on main.")
    monkeypatch.setattr(
        security_scanning, "verify_codeql_status", AsyncMock(return_value=gate)
    )
    verify_live = AsyncMock(return_value=live)
    monkeypatch.setattr(security_scanning, "verify_secure_deployment", verify_live)
    return verify_live


async def test_security_passes_when_both_gates_pass(monkeypatch):
    target = _job(SubmissionType.SECURITY_SCANNING).target
    assert target is not None
    live = ValidationResult(
        is_valid=True,
        message="HTTPS only.",
        task_results=[
            TaskResult(task_name="https-only", passed=True, feedback="Refused."),
            TaskResult(task_name="hsts", passed=True, feedback="HSTS sent."),
        ],
    )
    verify_live = _security_gates(monkeypatch, live)
    github = FakeGitHub()

    result = await security_scanning.verify_security_scanning(target, github)

    verify_live.assert_awaited_once_with(target.owner, target.repo, github)
    assert result.is_valid
    assert result.message == "CodeQL green on main. HTTPS only."
    assert [t.task_name for t in result.task_results or []] == [
        "codeql",
        "https-only",
        "hsts",
    ]
    assert all(t.passed for t in result.task_results or [])


@pytest.mark.parametrize("completed", [True, False])
async def test_security_live_failure_fails_with_combined_tasks(monkeypatch, completed):
    target = _job(SubmissionType.SECURITY_SCANNING).target
    assert target is not None
    https_only = TaskResult(task_name="https-only", passed=False, feedback="200.")
    hsts = TaskResult(task_name="hsts", passed=False, feedback="Missing.")
    live = ValidationResult(
        is_valid=False,
        verification_completed=completed,
        message="Not locked to HTTPS.",
        task_results=[https_only, hsts],
    )
    _security_gates(monkeypatch, live)

    result = await security_scanning.verify_security_scanning(target, FakeGitHub())

    assert not result.is_valid
    assert result.verification_completed is completed
    assert result.message == "Not locked to HTTPS."
    assert [t.task_name for t in result.task_results or []] == [
        "codeql",
        "https-only",
        "hsts",
    ]
