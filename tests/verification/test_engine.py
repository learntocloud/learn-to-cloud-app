"""Tests for the verification engine."""

import asyncio
import json
import logging
import traceback
from unittest.mock import AsyncMock, Mock
from uuid import uuid4

import httpx
import pytest
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import (
    InMemorySpanExporter,
)
from opentelemetry.trace import Status, StatusCode

from learn_to_cloud.models import SubmissionType
from learn_to_cloud.schemas.verification import TaskResult, ValidationResult
from learn_to_cloud.verification import engine as engine_module
from learn_to_cloud.verification import github_api, github_errors, security_scanning
from learn_to_cloud.verification.attempt_types import (
    PreparedVerificationAttempt,
)
from learn_to_cloud.verification.core import (
    CheckResult,
)
from learn_to_cloud.verification.deployed_api import DeployedApiServerError
from learn_to_cloud.verification.engine import run_verification
from learn_to_cloud.verification.evidence import apply_evidence_cap
from learn_to_cloud.verification.submission_values import submitted_value_from_raw
from learn_to_cloud.verification.tasks.phase6 import (
    SECURITY_SCANNING_RUBRIC_TASK,
)
from learn_to_cloud.verification.tasks.phase7 import (
    CAREER_REFLECTION_RUBRIC_TASK,
)
from tests.support.fakes.github import FakeGitHub
from tests.support.requirement_factories import (
    career_reflection_requirement,
    ctf_token_requirement,
    deployed_api_requirement,
    devops_analysis_requirement,
    journal_api_verifier_requirement,
    make_requirement,
    networking_token_requirement,
    profile_readme_requirement,
    repo_fork_requirement,
    security_scanning_requirement,
)


@pytest.fixture(autouse=True)
def repository_metadata(monkeypatch):
    metadata = _github()
    monkeypatch.setattr(engine_module, "GitHubClient", lambda: metadata)
    return metadata


def _github(**kwargs) -> FakeGitHub:
    repos = {
        f"learner/{name}": {
            "owner": {"id": 1, "login": "learner"},
            "name": name,
            "private": False,
        }
        for name in (
            "learner",
            "test-repo",
            "journal-starter",
            "devops-repo",
            "sec-repo",
        )
    }
    return FakeGitHub(repos=repos, **kwargs)


class _Span:
    def __init__(self) -> None:
        self.attributes: dict[str, object] = {}
        self.status: Status | None = None

    def __enter__(self):
        return self

    def __exit__(self, _exc_type, _exc, _traceback) -> bool:
        return False

    def set_attribute(self, key: str, value: object) -> None:
        self.attributes[key] = value

    def set_status(self, status: Status) -> None:
        self.status = status


class _Tracer:
    def __init__(self) -> None:
        self.spans: list[tuple[str, _Span, dict[str, object]]] = []

    def start_as_current_span(self, name: str, **kwargs) -> _Span:
        span = _Span()
        span.attributes.update(kwargs.get("attributes", {}))
        self.spans.append((name, span, kwargs))
        return span


@pytest.fixture
def step_spans(monkeypatch):

    exporter = InMemorySpanExporter()
    provider = TracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    monkeypatch.setattr(
        engine_module, "_tracer", provider.get_tracer(engine_module.__name__)
    )
    yield exporter
    provider.shutdown()


def _job(requirement=None) -> PreparedVerificationAttempt:
    requirement = requirement or repo_fork_requirement()
    return PreparedVerificationAttempt(
        id=uuid4(),
        user_id=1,
        github_username="learner",
        requirement=requirement,
        submitted_value=submitted_value_from_raw(
            requirement, "https://github.com/learner/test-repo"
        ),
    )


async def test_run_check_passes_inputs_and_preserves_result(monkeypatch):
    result = CheckResult(
        validation_result=ValidationResult(is_valid=True, message="Unchanged"),
    )
    dispatch = AsyncMock(return_value=result)
    monkeypatch.setattr(engine_module, "_dispatch", dispatch)
    job = _job()
    github = FakeGitHub()

    assert await engine_module._run_check(job, None, github) is result
    dispatch.assert_awaited_once_with(job, None, github)


@pytest.mark.asyncio
async def test_run_verification_runs_the_submission_types_check(
    monkeypatch, repository_metadata
):
    gate = AsyncMock(
        return_value=CheckResult(
            validation_result=ValidationResult(
                is_valid=True,
                message="Gate passed",
                task_results=[TaskResult(task_name="Gate", passed=True, feedback="ok")],
            ),
        )
    )

    monkeypatch.setattr(engine_module, "_dispatch", gate)
    tracer = _Tracer()
    monkeypatch.setattr(engine_module, "_tracer", tracer)

    job = _job()
    result = await run_verification(job)

    gate.assert_awaited_once()
    called_job, repository, github = gate.await_args_list[0].args
    assert called_job is job
    assert repository.target == job.target
    assert github is repository_metadata
    assert result.validation_result.is_valid is True
    assert result.validation_result.task_results == [
        TaskResult(task_name="Gate", passed=True, feedback="ok")
    ]
    assert len(tracer.spans) == 2
    _, ownership_span, _ = tracer.spans[0]
    assert ownership_span.attributes == {
        "verification.check.name": "github_repository_ownership",
        "verification.step.result": "passed",
    }
    name, span, _ = tracer.spans[-1]
    assert name == "verification.step"
    assert span.attributes == {
        "verification.check.name": "repo_fork",
        "verification.step.result": "passed",
    }


@pytest.mark.asyncio
async def test_step_span_records_native_exception(monkeypatch, step_spans):
    explode = AsyncMock(side_effect=RuntimeError("Unexpected step failure"))

    monkeypatch.setattr(engine_module, "_dispatch", explode)
    with pytest.raises(RuntimeError, match="Unexpected step failure"):
        await run_verification(_job())

    span = step_spans.get_finished_spans()[-1]
    assert span.attributes == {"verification.check.name": "repo_fork"}
    assert span.status is not None
    assert span.status.status_code is StatusCode.ERROR
    (event,) = span.events
    assert event.name == "exception"
    assert event.attributes["exception.type"] == "RuntimeError"
    assert event.attributes["exception.message"] == "Unexpected step failure"
    assert "_run_check" in event.attributes["exception.stacktrace"]


_REPOSITORY_TYPES = {
    SubmissionType.PROFILE_README,
    SubmissionType.REPO_FORK,
    SubmissionType.JOURNAL_API_VERIFIER,
    SubmissionType.DEVOPS_ANALYSIS,
    SubmissionType.SECURITY_SCANNING,
}


@pytest.mark.asyncio
@pytest.mark.parametrize("submission_type", list(SubmissionType))
async def test_shared_preflight_covers_only_repository_assignments(
    monkeypatch, repository_metadata, submission_type
):
    job = _job(make_requirement(submission_type))
    lookup = AsyncMock(
        return_value={
            "owner": {"id": 99, "login": "someone-else"},
            "name": "repo",
            "private": False,
        }
    )
    monkeypatch.setattr(repository_metadata, "repo_metadata", lookup)
    step = AsyncMock(
        return_value=CheckResult(
            validation_result=ValidationResult(is_valid=False, message="existing gate"),
        )
    )
    monkeypatch.setattr(engine_module, "_run_check", step)

    result = await run_verification(job)

    if submission_type in _REPOSITORY_TYPES:
        assert job.target is not None
        assert job.target is not None
        lookup.assert_awaited_once_with(job.target.owner, job.target.repo)
        step.assert_not_awaited()
        assert result.validation_result.username_match is False
        assert (
            "Use the required repository under the GitHub account you signed in with."
            in result.validation_result.message
        )
    else:
        lookup.assert_not_awaited()
        step.assert_awaited_once()
        assert result.validation_result.message == "existing gate"
    assert result.grading_requests == []


@pytest.mark.asyncio
async def test_canonical_repository_reaches_capstone_without_source_reads(
    monkeypatch, repository_metadata
):

    lookup = AsyncMock(
        return_value={
            "owner": {"id": 1, "login": "new-name"},
            "name": "moved-repo",
            "private": False,
        }
    )
    monkeypatch.setattr(repository_metadata, "repo_metadata", lookup)
    ci = AsyncMock(return_value=ValidationResult(is_valid=True, message="CI is green"))
    monkeypatch.setattr(engine_module, "verify_ci_status", ci)
    job = _journal_job()

    result = await run_verification(job)

    lookup.assert_awaited_once_with("learner", "journal-starter")
    ci.assert_awaited_once_with("new-name", "moved-repo", repository_metadata)
    assert not result.grading_requests
    assert result.attempt is job
    assert result.attempt.github_username == "learner"
    assert result.validation_result.message == "CI is green"
    assert result.validation_result.task_results is None


@pytest.mark.asyncio
@pytest.mark.parametrize("scenario", ["passed", "failed", "unavailable", "malformed"])
async def test_ownership_exports_bounded_telemetry(
    monkeypatch, repository_metadata, caplog, scenario
):

    exporter = InMemorySpanExporter()
    provider = TracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    monkeypatch.setattr(engine_module, "_tracer", provider.get_tracer("ownership-test"))
    response = httpx.Response(
        403,
        request=httpx.Request(
            "GET", "https://api.github.com/repos/private-name/private-repo"
        ),
        headers={"retry-after": "120"},
    )
    lookup = AsyncMock(
        return_value={
            "owner": {
                "id": 1 if scenario == "passed" else 987654321,
                "login": "private-name",
            },
            "name": "private-repo",
            "private": False,
        }
    )
    if scenario == "unavailable":
        lookup.side_effect = httpx.HTTPStatusError(
            "private-provider-body private-token",
            request=response.request,
            response=response,
        )
    elif scenario == "malformed":
        lookup.return_value = {"owner": "private-provider-body"}
    monkeypatch.setattr(repository_metadata, "repo_metadata", lookup)
    monkeypatch.setattr(
        engine_module,
        "_run_check",
        AsyncMock(
            return_value=CheckResult(
                validation_result=ValidationResult(is_valid=True, message="unchanged"),
            )
        ),
    )
    try:
        result = await run_verification(_job())
        (span,) = exporter.get_finished_spans()
        expected = "unavailable" if scenario == "malformed" else scenario
        assert span.attributes is not None
        assert span.name == "verification.step"
        assert (
            span.attributes["verification.check.name"] == "github_repository_ownership"
        )
        assert span.attributes["verification.step.result"] == expected
        assert span.status.status_code is (
            StatusCode.ERROR if expected == "unavailable" else StatusCode.UNSET
        )
        assert result.validation_result.verification_completed == (
            expected != "unavailable"
        )
        exported = span.to_json() + caplog.text
        for sentinel in (
            "private-name",
            "private-repo",
            "987654321",
            "private-provider-body",
            "private-token",
        ):
            assert sentinel not in exported
        assert not any(event.name == "exception" for event in span.events)
    finally:
        provider.shutdown()


@pytest.mark.parametrize("error_type", [RuntimeError, asyncio.CancelledError])
async def test_ownership_failure_keeps_native_diagnostics_and_correlation(
    monkeypatch, repository_metadata, caplog, error_type, step_spans
):
    tracer = engine_module._tracer
    error = error_type("Repository metadata parser failed")

    def fail_lookup(*_args):
        raise error

    lookup = AsyncMock(side_effect=fail_lookup)
    monkeypatch.setattr(repository_metadata, "repo_metadata", lookup)
    step = AsyncMock()
    monkeypatch.setattr(engine_module, "_run_check", step)
    counter = Mock()
    monkeypatch.setattr(github_errors, "_GITHUB_API_ERROR_COUNTER", counter)
    evidence_decision = Mock()
    monkeypatch.setattr(engine_module, "record_evidence_decision", evidence_decision)
    job = _job()

    with (
        caplog.at_level(logging.INFO),
        tracer.start_as_current_span(
            "verification.attempt",
            attributes={"verification.attempt.id": str(job.id)},
        ),
        pytest.raises(error_type) as raised,
    ):
        await run_verification(job)

    assert raised.value is error
    assert "fail_lookup" in {
        frame.name for frame in traceback.extract_tb(raised.value.__traceback__)
    }
    assert job.target is not None
    lookup.assert_awaited_once_with(job.target.owner, job.target.repo)
    step.assert_not_awaited()
    counter.add.assert_not_called()
    evidence_decision.assert_not_called()
    ownership_span, attempt_span = step_spans.get_finished_spans()
    assert ownership_span.name == "verification.step"
    assert ownership_span.parent.span_id == attempt_span.context.span_id
    assert ownership_span.context.trace_id == attempt_span.context.trace_id
    assert attempt_span.attributes["verification.attempt.id"] == str(job.id)
    assert ownership_span.attributes["verification.check.name"] == (
        "github_repository_ownership"
    )
    assert ownership_span.status.status_code == (
        StatusCode.ERROR if error_type is RuntimeError else StatusCode.UNSET
    )
    if error_type is RuntimeError:
        (event,) = ownership_span.events
        assert event.attributes["exception.message"] == str(error)
        assert "fail_lookup" in event.attributes["exception.stacktrace"]
    else:
        assert not ownership_span.events
    assert not attempt_span.events
    assert "verification.attempt.completed" not in caplog.text


# ---------------------------------------------------------------------------
# Phase 3 journal API: current-commit capstone CI gate.
# ---------------------------------------------------------------------------


def _journal_job() -> PreparedVerificationAttempt:

    requirement = journal_api_verifier_requirement(
        slug="journal-api-implementation",
        name="Journal API Implementation",
        required_repo="owner/journal-starter",
    )
    return PreparedVerificationAttempt(
        id=uuid4(),
        user_id=1,
        github_username="learner",
        requirement=requirement,
        submitted_value=submitted_value_from_raw(
            requirement, "https://github.com/learner/journal-starter"
        ),
    )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("passed", "completed"), [(True, True), (False, True), (False, False)]
)
async def test_journal_workflow_never_collects_source_or_requests_grading(
    monkeypatch, repository_metadata, passed, completed
):
    gate_result = ValidationResult(
        is_valid=passed, verification_completed=completed, message="Capstone result"
    )
    gate = AsyncMock(return_value=gate_result)
    monkeypatch.setattr(engine_module, "verify_ci_status", gate)
    job = _journal_job()
    result = await run_verification(job)
    gate.assert_awaited_once_with("learner", "journal-starter", repository_metadata)
    assert result.validation_result == gate_result
    assert result.grading_requests == []


# ---------------------------------------------------------------------------
# Phase 4/5 deterministic checks: deployed API probe and DevOps pipeline.
# ---------------------------------------------------------------------------


def _deployed_api_job() -> PreparedVerificationAttempt:

    requirement = deployed_api_requirement(slug="deployed-api")
    return PreparedVerificationAttempt(
        id=uuid4(),
        user_id=1,
        github_username=None,
        requirement=requirement,
        submitted_value=submitted_value_from_raw(
            requirement, "https://api.example.com"
        ),
    )


def _devops_job() -> PreparedVerificationAttempt:

    requirement = devops_analysis_requirement(
        slug="devops-analysis",
        required_repo="owner/devops-repo",
    )
    return PreparedVerificationAttempt(
        id=uuid4(),
        user_id=1,
        github_username="learner",
        requirement=requirement,
        submitted_value=submitted_value_from_raw(
            requirement, "https://github.com/learner/devops-repo"
        ),
    )


@pytest.mark.asyncio
async def test_deployed_api_workflow_passes_through_deterministic_result(monkeypatch):
    validate = AsyncMock(
        return_value=ValidationResult(is_valid=True, message="API is healthy")
    )
    monkeypatch.setattr(engine_module, "validate_deployed_api", validate)

    result = await run_verification(_deployed_api_job())

    validate.assert_awaited_once_with("https://api.example.com")
    assert result.validation_result.is_valid is True
    assert result.validation_result.message == "API is healthy"
    assert result.grading_requests == []


@pytest.mark.asyncio
async def test_deployed_api_workflow_fails_when_probe_fails(monkeypatch):
    validate = AsyncMock(
        return_value=ValidationResult(is_valid=False, message="API unreachable")
    )
    monkeypatch.setattr(engine_module, "validate_deployed_api", validate)

    result = await run_verification(_deployed_api_job())

    validate.assert_awaited_once_with("https://api.example.com")
    assert result.validation_result.is_valid is False
    assert result.grading_requests == []


@pytest.mark.parametrize(
    ("passed", "completed"), [(True, True), (False, True), (False, False)]
)
async def test_devops_workflow_uses_only_run_results(
    monkeypatch, repository_metadata, passed, completed
):
    validation = ValidationResult(
        is_valid=passed, verification_completed=completed, message="Pipeline result"
    )
    verify = AsyncMock(return_value=validation)
    monkeypatch.setattr(engine_module, "verify_devops_pipeline", verify)

    result = await run_verification(_devops_job())

    verify.assert_awaited_once_with("learner", "devops-repo", repository_metadata)
    assert result.validation_result is validation
    assert result.grading_requests == []


# ---------------------------------------------------------------------------
# Phase 6/7 rubric checks: security scanning gates repository evidence;
# career reflection prepares submitted text for grading.
# ---------------------------------------------------------------------------


def _security_job() -> PreparedVerificationAttempt:

    requirement = security_scanning_requirement(
        slug="security-scanning",
        required_repo="owner/sec-repo",
    )
    return PreparedVerificationAttempt(
        id=uuid4(),
        user_id=1,
        github_username="learner",
        requirement=requirement,
        submitted_value=submitted_value_from_raw(
            requirement, "https://github.com/learner/sec-repo"
        ),
    )


def _career_job(text: str) -> PreparedVerificationAttempt:

    requirement = career_reflection_requirement(slug="career-reflection")
    return PreparedVerificationAttempt(
        id=uuid4(),
        user_id=1,
        github_username=None,
        requirement=requirement,
        submitted_value=submitted_value_from_raw(requirement, text),
    )


@pytest.mark.asyncio
async def test_security_workflow_records_grading_request_when_gate_passes(monkeypatch):

    gate = AsyncMock(
        return_value=ValidationResult(is_valid=True, message="CodeQL green on main")
    )
    monkeypatch.setattr(security_scanning, "verify_codeql_status", gate)
    github = _github(
        files={".github/workflows/codeql.yml": "name: CodeQL\non: [push]\n"}
    )

    result = await run_verification(_security_job(), github=github)

    gate.assert_awaited_once_with("learner", "sec-repo", github)
    assert result.validation_result.is_valid is True
    assert result.grading_requests is not None
    assert result.grading_requests is not None
    assert len(result.grading_requests) == 1
    assert result.grading_requests[0].task.id == SECURITY_SCANNING_RUBRIC_TASK.id


@pytest.mark.asyncio
async def test_security_workflow_skips_grading_when_gate_fails(monkeypatch):

    gate = AsyncMock(
        return_value=ValidationResult(is_valid=False, message="No CodeQL runs found")
    )
    monkeypatch.setattr(security_scanning, "verify_codeql_status", gate)

    github = _github()
    result = await run_verification(_security_job(), github=github)

    gate.assert_awaited_once_with("learner", "sec-repo", github)
    assert result.validation_result.is_valid is False
    assert result.grading_requests == []


def _evidence_flow(monkeypatch):
    passing = ValidationResult(is_valid=True, message="Prerequisite passed.")
    monkeypatch.setattr(
        security_scanning, "verify_codeql_status", AsyncMock(return_value=passing)
    )
    policy = SECURITY_SCANNING_RUBRIC_TASK.evidence
    return _security_job(), [*policy.required_files, *policy.optional_files]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("failure", "category"),
    [
        (401, "authentication"),
        (403, "authorization"),
        (429, "rate_limit"),
        (503, "provider_unavailable"),
        ("network", "timeout.read"),
    ],
)
async def test_failed_evidence_read_stops_grading(monkeypatch, failure, category):
    job, paths = _evidence_flow(monkeypatch)
    paths = sorted(paths)
    failed_path = paths[1]
    fetched = []
    mapper = Mock(wraps=github_errors.github_error_to_result)
    monkeypatch.setattr(security_scanning, "github_error_to_result", mapper)
    counter = Mock()
    monkeypatch.setattr(github_errors, "_GITHUB_API_ERROR_COUNTER", counter)
    tracer = _Tracer()
    monkeypatch.setattr(engine_module, "_tracer", tracer)

    def respond(request):
        if request.url.host == "api.github.com":
            if request.url.path == "/repos/learner/sec-repo":
                return httpx.Response(
                    200,
                    json={
                        "owner": {"id": 1, "login": "learner"},
                        "name": "sec-repo",
                        "private": False,
                    },
                )
            return httpx.Response(
                200, json={"tree": [{"type": "blob", "path": p} for p in paths]}
            )
        path = request.url.path.split("/main/", 1)[1]
        fetched.append(path)
        if path != failed_path:
            return httpx.Response(200, text="Evidence content")
        if failure == "network":
            raise httpx.ReadTimeout("private connection details", request=request)
        return httpx.Response(failure, text="private response details")

    async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as client:
        monkeypatch.setattr(
            github_api, "get_github_client", AsyncMock(return_value=client)
        )
        monkeypatch.setattr(
            "learn_to_cloud.verification.github_http._get_github_client",
            AsyncMock(return_value=client),
        )
        result = await run_verification(job, github=github_api.GitHubClient())

    assert fetched == paths[:2]
    assert result.validation_result.is_valid is False
    assert result.validation_result.verification_completed is False
    assert "private" not in result.validation_result.message
    assert result.grading_requests == []
    mapper.assert_called_once()
    assert mapper.call_args.kwargs == {"event": "security_scanning.repo_file_error"}
    counter.add.assert_called_once_with(1, {"error.type": category})
    assert tracer.spans[0][1].attributes["verification.step.result"] == "passed"
    assert tracer.spans[-1][1].attributes["verification.step.result"] == "unavailable"
    assert tracer.spans[-1][1].status is not None
    assert tracer.spans[-1][1].status.status_code is StatusCode.ERROR


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "error",
    [
        RuntimeError("programming bug"),
        DeployedApiServerError("another integration", status_code=503),
    ],
)
async def test_evidence_boundaries_do_not_swallow_unsupported_errors(
    monkeypatch, error
):
    job, paths = _evidence_flow(monkeypatch)
    github = _github(files=dict.fromkeys(paths, "evidence"))
    monkeypatch.setattr(github, "file", AsyncMock(side_effect=error))
    mapper = Mock(wraps=github_errors.github_error_to_result)
    monkeypatch.setattr(security_scanning, "github_error_to_result", mapper)

    with pytest.raises(type(error)) as raised:
        await run_verification(job, github=github)

    assert raised.value is error
    mapper.assert_not_called()


@pytest.mark.asyncio
async def test_selected_evidence_disappearance_blocks_grading(monkeypatch):
    job, paths = _evidence_flow(monkeypatch)
    contents = dict.fromkeys(paths, "evidence")
    missing_path = paths[1]
    del contents[missing_path]
    github = _github(files=contents, tree=paths)

    result = await run_verification(job, github=github)

    assert result.validation_result.verification_completed is False
    assert result.validation_result.error_code == "evidence.changed"
    assert result.grading_requests == []


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "error",
    [
        github_errors.GitHubServerError("Unavailable", status_code=503),
        httpx.ConnectError("private connection details"),
    ],
)
async def test_tree_failure_stops_grading_with_tree_event(monkeypatch, error):
    job, _ = _evidence_flow(monkeypatch)
    mapper = Mock(wraps=github_errors.github_error_to_result)
    monkeypatch.setattr(security_scanning, "github_error_to_result", mapper)
    github = _github(tree_error=error)
    read = AsyncMock()
    monkeypatch.setattr(github, "file", read)

    result = await run_verification(job, github=github)

    assert result.validation_result.verification_completed is False
    assert result.grading_requests == []
    mapper.assert_called_once_with(error, event="security_scanning.repo_file_error")
    read.assert_not_awaited()


async def test_repository_rubric_blocks_oversized_evidence(monkeypatch):
    job, paths = _evidence_flow(monkeypatch)
    files = dict.fromkeys(paths, "complete")
    files[paths[0]] = "x" * (51 * 1024)
    result = await run_verification(job, github=_github(files=files))
    assert result.validation_result.error_code == "evidence.item_limit"
    assert not result.validation_result.is_valid
    assert not result.validation_result.verification_completed
    assert result.grading_requests == []


async def test_oversized_reflection_is_incomplete_without_any_repository_read():
    repo = AsyncMock()
    result = await run_verification(
        _career_job("🦊" * (20 * 1024 // 4 + 1)),
        github=repo,
    )
    assert result.validation_result.error_code == "evidence.item_limit"
    assert not result.validation_result.is_valid
    assert not result.validation_result.verification_completed
    assert result.grading_requests == []
    repo.tree.assert_not_awaited()
    repo.file.assert_not_awaited()


async def test_absent_optional_work_still_prepares_complete_grading(monkeypatch):
    job, paths = _evidence_flow(monkeypatch)
    task = SECURITY_SCANNING_RUBRIC_TASK
    files = {
        path: "complete" for path in paths if path not in task.evidence.optional_files
    }
    result = await run_verification(job, github=_github(files=files))
    assert result.validation_result.is_valid
    assert result.grading_requests is not None
    assert len(result.grading_requests) == 1
    prompt = json.loads(result.grading_requests[0].message.split("\n\n", 1)[1])
    assert prompt["evidence"]["optional_presence"] == dict.fromkeys(
        task.evidence.optional_files,
        False,
    )


@pytest.mark.parametrize("mutation", ["truncated", "missing", "wrong_task"])
async def test_engine_rechecks_collector_result_before_recording_grading(
    monkeypatch, mutation
):

    job = _career_job("Complete reflection")
    task = CAREER_REFLECTION_RUBRIC_TASK
    bundle = apply_evidence_cap(task, [("career-reflection.md", "Complete reflection")])
    if mutation == "truncated":
        bundle = bundle.model_copy(
            update={
                "items": [bundle.items[0].model_copy(update={"truncated": True})],
            }
        )
    elif mutation == "missing":
        bundle = bundle.model_copy(update={"items": []})
    else:
        bundle = bundle.model_copy(update={"task_id": "other-task"})
    monkeypatch.setattr(
        engine_module, "collect_submitted_text_evidence", lambda *_: bundle
    )
    result = await run_verification(job)
    assert result.validation_result.error_code == "evidence.selection"
    assert not result.validation_result.verification_completed
    assert result.grading_requests == []


@pytest.mark.asyncio
async def test_career_workflow_prepares_text_grading(monkeypatch):

    text = "A specific, first-person reflection on my target role and projects."
    tracer = _Tracer()
    monkeypatch.setattr(engine_module, "_tracer", tracer)
    result = await run_verification(_career_job(text))

    assert result.validation_result.is_valid is True
    assert result.validation_result.message == (
        "Reflection received. Reviewing your answers."
    )
    assert result.grading_requests is not None
    assert result.grading_requests is not None
    assert len(result.grading_requests) == 1
    request = result.grading_requests[0]
    assert request.task.id == CAREER_REFLECTION_RUBRIC_TASK.id
    assert request.task.evidence.source == "submitted_text"
    assert text in request.message
    assert len(tracer.spans) == 1
    assert tracer.spans[0][1].attributes == {
        "verification.check.name": "career_reflection",
        "verification.step.result": "passed",
    }


# ---------------------------------------------------------------------------
# Phase 0-2 deterministic checks: profile README, repo fork, CTF and networking
# tokens. All are deterministic (no grading) and require a GitHub username.
# ---------------------------------------------------------------------------


def _phase02_job(requirement, submitted_value, github_username="learner"):
    return PreparedVerificationAttempt(
        id=uuid4(),
        user_id=1,
        github_username=github_username,
        requirement=requirement,
        submitted_value=submitted_value_from_raw(requirement, submitted_value),
    )


async def test_profile_readme_passes_from_the_ownership_lookup_alone(
    repository_metadata, monkeypatch
):
    lookup = AsyncMock(wraps=repository_metadata.repo_metadata)
    monkeypatch.setattr(repository_metadata, "repo_metadata", lookup)
    job = _phase02_job(
        profile_readme_requirement(),
        "https://github.com/learner/learner",
    )

    result = await run_verification(job)

    lookup.assert_awaited_once_with("learner", "learner")
    assert result.validation_result.is_valid is True
    assert result.validation_result.message == "Profile README validated successfully!"
    assert result.grading_requests == []


@pytest.mark.parametrize(
    ("fork_fields", "valid"),
    [
        ({"fork": True, "parent": {"full_name": "upstream/test-repo"}}, True),
        ({"fork": True, "parent": {"full_name": "other/test-repo"}}, False),
        ({"fork": False}, False),
    ],
)
async def test_repo_fork_uses_the_ownership_lookup_alone(
    repository_metadata, monkeypatch, fork_fields, valid
):
    lookup = AsyncMock(
        return_value={
            "owner": {"id": 1, "login": "learner"},
            "name": "test-repo",
            "private": False,
            **fork_fields,
        }
    )
    monkeypatch.setattr(repository_metadata, "repo_metadata", lookup)
    job = _phase02_job(
        repo_fork_requirement(required_repo="upstream/test-repo"),
        "https://github.com/learner/test-repo",
    )

    result = await run_verification(job)

    lookup.assert_awaited_once_with("learner", "test-repo")
    assert result.validation_result.is_valid is valid
    assert result.validation_result.verification_completed
    assert result.grading_requests == []


@pytest.mark.asyncio
async def test_ctf_token_workflow_passes_through_validator(monkeypatch):

    captured: dict[str, str] = {}

    def fake_ctf(token, username):
        captured["token"] = token
        captured["username"] = username
        return ValidationResult(is_valid=True, message="CTF token valid")

    monkeypatch.setattr(engine_module, "verify_ctf_token", fake_ctf)

    job = _phase02_job(ctf_token_requirement(), "the-token")
    result = await run_verification(job)

    assert result.validation_result.is_valid is True
    assert result.grading_requests == []
    assert captured == {"token": "the-token", "username": "learner"}


@pytest.mark.asyncio
async def test_networking_token_workflow_passes_through_validator(monkeypatch):

    sentinel = ValidationResult(is_valid=False, message="Networking token invalid")
    verify = Mock(return_value=sentinel)
    monkeypatch.setattr(engine_module, "verify_networking_token", verify)

    job = _phase02_job(networking_token_requirement(), "bad-token")
    result = await run_verification(job)

    verify.assert_called_once_with("bad-token", "learner")
    assert result.validation_result is sentinel
    assert result.grading_requests == []


@pytest.mark.asyncio
async def test_workflow_requiring_username_short_circuits_when_missing():

    job = _phase02_job(ctf_token_requirement(), "the-token", github_username=None)
    result = await run_verification(job)

    assert result.validation_result.is_valid is False
    assert result.validation_result.username_match is False
    assert "GitHub username is required" in result.validation_result.message
    assert result.grading_requests == []
