"""Tests for the declarative verification engine."""

import asyncio
import json
import logging
import traceback
from dataclasses import replace
from functools import partial
from unittest.mock import AsyncMock, Mock
from uuid import uuid4

import httpx
import pytest
from learn_to_cloud_shared_test_support.requirement_factories import (
    make_requirement,
    repo_fork_requirement,
)
from opentelemetry.trace import Status, StatusCode

from learn_to_cloud_shared.models import SubmissionType
from learn_to_cloud_shared.schemas import TaskResult, ValidationResult
from learn_to_cloud_shared.submission_values import submitted_value_from_raw
from learn_to_cloud_shared.verification import engine as engine_module
from learn_to_cloud_shared.verification import github_errors
from learn_to_cloud_shared.verification import repo_files as repo_files_module
from learn_to_cloud_shared.verification import workflows as workflows_module
from learn_to_cloud_shared.verification.checks import career as career_checks
from learn_to_cloud_shared.verification.checks import (
    deployed_api as deployed_api_checks,
)
from learn_to_cloud_shared.verification.checks import devops as devops_checks
from learn_to_cloud_shared.verification.checks import github as github_checks
from learn_to_cloud_shared.verification.checks import security as security_checks
from learn_to_cloud_shared.verification.checks import tokens as tokens_checks
from learn_to_cloud_shared.verification.core import (
    CheckFn,
    Step,
    StepContext,
    StepResult,
    VerificationWorkflow,
)
from learn_to_cloud_shared.verification.deployed_api import DeployedApiServerError
from learn_to_cloud_shared.verification.engine import run_verification
from learn_to_cloud_shared.verification.grading_requests import LLMGradingRequest
from learn_to_cloud_shared.verification.repo_files import (
    GitHubRepoFiles,
)
from learn_to_cloud_shared.verification.tasks.phase6 import (
    SECURITY_SCANNING_RUBRIC_TASK,
)
from learn_to_cloud_shared.verification.tasks.phase7 import (
    CAREER_REFLECTION_RUBRIC_TASK,
)
from learn_to_cloud_shared.verification_workflow import (
    PreparedVerificationAttempt,
)
from tests.fakes.github_metadata import InMemoryGitHubMetadata
from tests.fakes.repo_files import InMemoryRepoFiles


@pytest.fixture(autouse=True)
def repository_metadata(monkeypatch):
    metadata = InMemoryGitHubMetadata(
        repos={
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
    )
    monkeypatch.setattr(
        "learn_to_cloud_shared.verification.repository_ownership.GitHubApiMetadata",
        lambda: metadata,
    )
    return metadata


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
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import SimpleSpanProcessor
    from opentelemetry.sdk.trace.export.in_memory_span_exporter import (
        InMemorySpanExporter,
    )

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


def _step(check: CheckFn, task_id: str, *, name: str = "test_check") -> Step:
    return Step(name=name, task_id=task_id, check=check)


def _workflow(*steps: Step) -> VerificationWorkflow:
    return VerificationWorkflow(requires_username=False, steps=steps)


def test_workflow_requires_an_authoritative_validation_result():
    with pytest.raises(ValueError, match="without a validation result"):
        engine_module._aggregate([StepResult(passed=True)])


def test_non_rubric_workflow_rejects_grading_requests():
    request = LLMGradingRequest(
        task=CAREER_REFLECTION_RUBRIC_TASK, message="unexpected grading request"
    )
    with pytest.raises(ValueError, match="Non-rubric workflow"):
        engine_module._validate_grading_requests(_workflow(), [], [request])


def test_successful_rubric_workflow_requires_a_grading_request():
    workflow = VerificationWorkflow(
        requires_username=False, rubric=CAREER_REFLECTION_RUBRIC_TASK.grader
    )
    with pytest.raises(ValueError, match="without a grading request"):
        engine_module._validate_grading_requests(
            workflow, [StepResult(passed=True)], []
        )


@pytest.mark.parametrize("configured", [False, True])
async def test_step_preserves_callback_context_and_result_identity(configured):
    result = StepResult(
        passed=True,
        validation_result=ValidationResult(is_valid=True, message="Unchanged"),
    )
    check = AsyncMock(return_value=result)
    kwargs = {"task": CAREER_REFLECTION_RUBRIC_TASK} if configured else {}
    callback = partial(check, **kwargs) if configured else check
    job = _job()
    context = StepContext(
        job=job, repository=job.target, submitted_value=job.submitted_value
    )

    assert await engine_module._run_step(_step(callback, "gate"), context) is result
    check.assert_awaited_once_with(context, **kwargs)


@pytest.mark.asyncio
async def test_run_verification_uses_declared_steps(monkeypatch):
    async def _gate(context: StepContext) -> StepResult:
        return StepResult(
            passed=True,
            validation_result=ValidationResult(
                is_valid=True,
                message="Gate passed",
                task_results=[TaskResult(task_name="Gate", passed=True, feedback="ok")],
            ),
        )

    monkeypatch.setattr(
        engine_module,
        "workflow_for",
        lambda _t: _workflow(_step(_gate, "gate", name="test_gate_pass")),
    )
    tracer = _Tracer()
    monkeypatch.setattr(engine_module, "_tracer", tracer)

    result = await run_verification(_job())

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
        "verification.check.name": "test_gate_pass",
        "verification.task.id": "gate",
        "verification.step.result": "passed",
    }


@pytest.mark.asyncio
async def test_step_span_records_native_exception(monkeypatch, step_spans):
    async def _explode(context: StepContext) -> StepResult:
        raise RuntimeError("Unexpected step failure")

    monkeypatch.setattr(
        engine_module,
        "workflow_for",
        lambda _t: _workflow(_step(_explode, "explode", name="exploding")),
    )
    with pytest.raises(RuntimeError, match="Unexpected step failure"):
        await run_verification(_job())

    span = step_spans.get_finished_spans()[-1]
    assert span.attributes == {
        "verification.check.name": "exploding",
        "verification.task.id": "explode",
    }
    assert span.status is not None
    assert span.status.status_code is StatusCode.ERROR
    (event,) = span.events
    assert event.name == "exception"
    assert event.attributes["exception.type"] == "RuntimeError"
    assert event.attributes["exception.message"] == "Unexpected step failure"
    assert "_explode" in event.attributes["exception.stacktrace"]


@pytest.mark.asyncio
async def test_failed_gate_short_circuits(monkeypatch):
    ran: list[str] = []

    async def _first(context: StepContext) -> StepResult:
        ran.append("first")
        return StepResult(
            passed=False,
            validation_result=ValidationResult(is_valid=False, message="Gate failed"),
        )

    async def _second(context: StepContext) -> StepResult:
        ran.append("second")
        return StepResult(passed=True)

    monkeypatch.setattr(
        engine_module,
        "workflow_for",
        lambda _t: _workflow(
            _step(_first, "a"),
            _step(_second, "b"),
        ),
    )

    result = await run_verification(_job())

    assert ran == ["first"]
    assert result.validation_result.is_valid is False


def test_multiple_authoritative_results_keep_latest_message_and_all_feedback():
    first_task = TaskResult(task_name="Files", passed=True, feedback="present")
    second_task = TaskResult(task_name="Image", passed=True, feedback="pullable")

    result = engine_module._aggregate(
        [
            StepResult(
                passed=True,
                validation_result=ValidationResult(
                    is_valid=True,
                    message="Required files exist",
                    username_match=True,
                    task_results=[first_task],
                ),
            ),
            StepResult(
                passed=True,
                validation_result=ValidationResult(
                    is_valid=True,
                    message="Container image is pullable",
                    repo_exists=True,
                    task_results=[second_task],
                ),
            ),
        ]
    )

    assert result.is_valid is True
    assert result.message == "Container image is pullable"
    assert result.username_match is True
    assert result.repo_exists is True
    assert result.task_results == [first_task, second_task]


def test_later_authoritative_failure_is_not_hidden_by_an_earlier_pass():
    result = engine_module._aggregate(
        [
            StepResult(
                passed=True,
                validation_result=ValidationResult(
                    is_valid=True,
                    message="Required files exist",
                ),
            ),
            StepResult(
                passed=False,
                validation_result=ValidationResult(
                    is_valid=False,
                    message="Container image is not pullable",
                ),
            ),
        ]
    )

    assert result.is_valid is False
    assert result.message == "Container image is not pullable"


@pytest.mark.asyncio
async def test_unregistered_type_returns_unknown_result(monkeypatch):
    monkeypatch.setattr(engine_module, "workflow_for", lambda _t: None)

    result = await run_verification(_job())

    assert result.validation_result.is_valid is False
    assert "Unknown submission type" in result.validation_result.message
    assert result.grading_requests == []


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
        return_value=StepResult(
            passed=False,
            validation_result=ValidationResult(is_valid=False, message="existing gate"),
        )
    )
    monkeypatch.setattr(engine_module, "_run_step", step)

    result = await run_verification(job)

    if submission_type in _REPOSITORY_TYPES:
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
    from learn_to_cloud_shared.verification.repo_files import RepoFiles

    lookup = AsyncMock(
        return_value={
            "owner": {"id": 1, "login": "new-name"},
            "name": "moved-repo",
            "private": False,
        }
    )
    monkeypatch.setattr(repository_metadata, "repo_metadata", lookup)
    ci = AsyncMock(return_value=ValidationResult(is_valid=True, message="CI is green"))
    monkeypatch.setattr(github_checks, "verify_ci_status", ci)
    files = AsyncMock(spec=RepoFiles)
    job = _journal_job()

    result = await run_verification(job, repo_files=files)

    lookup.assert_awaited_once_with("learner", "journal-starter")
    ci.assert_awaited_once_with("new-name", "moved-repo")
    files.file.assert_not_awaited()
    files.tree.assert_not_awaited()
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
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import SimpleSpanProcessor
    from opentelemetry.sdk.trace.export.in_memory_span_exporter import (
        InMemorySpanExporter,
    )

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
        "_run_step",
        AsyncMock(
            return_value=StepResult(
                passed=True,
                validation_result=ValidationResult(is_valid=True, message="unchanged"),
            )
        ),
    )
    try:
        result = await run_verification(_job())
        (span,) = exporter.get_finished_spans()
        expected = "unavailable" if scenario == "malformed" else scenario
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
    monkeypatch.setattr(engine_module, "_run_step", step)
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
# Phase 3 journal API workflow: current-commit capstone workflow gate.
# ---------------------------------------------------------------------------


def _journal_job() -> PreparedVerificationAttempt:
    from learn_to_cloud_shared_test_support.requirement_factories import (
        journal_api_verifier_requirement,
    )

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
    monkeypatch, passed, completed
):
    gate_result = ValidationResult(
        is_valid=passed, verification_completed=completed, message="Capstone result"
    )
    gate = AsyncMock(return_value=gate_result)
    monkeypatch.setattr(github_checks, "verify_ci_status", gate)
    files = AsyncMock()
    job = _journal_job()
    workflow = engine_module.workflow_for(job.requirement.submission_type)
    assert len(workflow.steps) == 1
    assert workflow.rubric is None
    result = await run_verification(job, repo_files=files)
    gate.assert_awaited_once_with("learner", "journal-starter")
    files.tree.assert_not_awaited()
    files.file.assert_not_awaited()
    assert result.validation_result == gate_result
    assert result.grading_requests == []


# ---------------------------------------------------------------------------
# Phase 4/5 deterministic workflows: deployed API probe and DevOps workflow.
# ---------------------------------------------------------------------------


def _deployed_api_job() -> PreparedVerificationAttempt:
    from learn_to_cloud_shared_test_support.requirement_factories import (
        deployed_api_requirement,
    )

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
    from learn_to_cloud_shared_test_support.requirement_factories import (
        devops_analysis_requirement,
    )

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
    monkeypatch.setattr(deployed_api_checks, "validate_deployed_api", validate)

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
    monkeypatch.setattr(deployed_api_checks, "validate_deployed_api", validate)

    result = await run_verification(_deployed_api_job())

    validate.assert_awaited_once_with("https://api.example.com")
    assert result.validation_result.is_valid is False
    assert result.grading_requests == []


@pytest.mark.parametrize(
    ("passed", "completed"), [(True, True), (False, True), (False, False)]
)
async def test_devops_workflow_uses_only_run_results(monkeypatch, passed, completed):
    validation = ValidationResult(
        is_valid=passed, verification_completed=completed, message="Pipeline result"
    )
    verify = AsyncMock(return_value=validation)
    monkeypatch.setattr(devops_checks, "verify_devops_pipeline", verify)
    files = AsyncMock()

    result = await run_verification(_devops_job(), repo_files=files)

    verify.assert_awaited_once_with("learner", "devops-repo")
    files.tree.assert_not_awaited()
    files.file.assert_not_awaited()
    assert result.validation_result is validation
    assert result.grading_requests == []


# ---------------------------------------------------------------------------
# Phase 6/7 rubric workflows: security scanning gates repository evidence;
# career reflection prepares submitted text for grading.
# ---------------------------------------------------------------------------


def _security_job() -> PreparedVerificationAttempt:
    from learn_to_cloud_shared_test_support.requirement_factories import (
        security_scanning_requirement,
    )

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
    from learn_to_cloud_shared_test_support.requirement_factories import (
        career_reflection_requirement,
    )

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
    from learn_to_cloud_shared.verification.tasks.phase6 import (
        SECURITY_SCANNING_RUBRIC_TASK,
    )
    from tests.fakes.repo_files import InMemoryRepoFiles

    gate = AsyncMock(
        return_value=ValidationResult(is_valid=True, message="CodeQL green on main")
    )
    monkeypatch.setattr(security_checks, "verify_codeql_status", gate)
    repo_files = InMemoryRepoFiles(
        {".github/workflows/codeql.yml": "name: CodeQL\non: [push]\n"}
    )

    result = await run_verification(_security_job(), repo_files=repo_files)

    gate.assert_awaited_once_with("learner", "sec-repo")
    assert result.validation_result.is_valid is True
    assert result.grading_requests is not None
    assert len(result.grading_requests) == 1
    assert result.grading_requests[0].task.id == SECURITY_SCANNING_RUBRIC_TASK.id


@pytest.mark.asyncio
async def test_security_workflow_skips_grading_when_gate_fails(monkeypatch):
    from tests.fakes.repo_files import InMemoryRepoFiles

    gate = AsyncMock(
        return_value=ValidationResult(is_valid=False, message="No CodeQL runs found")
    )
    monkeypatch.setattr(security_checks, "verify_codeql_status", gate)

    result = await run_verification(_security_job(), repo_files=InMemoryRepoFiles({}))

    gate.assert_awaited_once_with("learner", "sec-repo")
    assert result.validation_result.is_valid is False
    assert result.grading_requests == []


def _evidence_flow(monkeypatch):
    passing = ValidationResult(is_valid=True, message="Prerequisite passed.")
    monkeypatch.setattr(
        security_checks, "verify_codeql_status", AsyncMock(return_value=passing)
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
        ("network", "network"),
    ],
)
async def test_failed_evidence_read_stops_grading(monkeypatch, failure, category):
    job, paths = _evidence_flow(monkeypatch)
    paths = sorted(paths)
    failed_path = paths[1]
    fetched = []
    mapper = Mock(wraps=github_errors.github_error_to_result)
    monkeypatch.setattr(security_checks, "github_error_to_result", mapper)
    counter = Mock()
    monkeypatch.setattr(github_errors, "_GITHUB_API_ERROR_COUNTER", counter)
    tracer = _Tracer()
    monkeypatch.setattr(engine_module, "_tracer", tracer)

    def respond(request):
        if request.url.host == "api.github.com":
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
            repo_files_module, "get_github_client", AsyncMock(return_value=client)
        )
        monkeypatch.setattr(
            "learn_to_cloud_shared.verification.github_http._get_github_client",
            AsyncMock(return_value=client),
        )
        result = await run_verification(job, repo_files=GitHubRepoFiles())

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
    files = InMemoryRepoFiles(dict.fromkeys(paths, "evidence"))
    monkeypatch.setattr(files, "file", AsyncMock(side_effect=error))
    mapper = Mock(wraps=github_errors.github_error_to_result)
    monkeypatch.setattr(security_checks, "github_error_to_result", mapper)

    with pytest.raises(type(error)) as raised:
        await run_verification(job, repo_files=files)

    assert raised.value is error
    mapper.assert_not_called()


@pytest.mark.asyncio
async def test_selected_evidence_disappearance_blocks_grading(monkeypatch):
    job, paths = _evidence_flow(monkeypatch)
    contents = dict.fromkeys(paths, "evidence")
    missing_path = paths[1]
    del contents[missing_path]
    files = InMemoryRepoFiles(contents, tree=paths)

    result = await run_verification(job, repo_files=files)

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
    monkeypatch.setattr(security_checks, "github_error_to_result", mapper)
    files = InMemoryRepoFiles(tree_error=error)
    read = AsyncMock()
    monkeypatch.setattr(files, "file", read)

    result = await run_verification(job, repo_files=files)

    assert result.validation_result.verification_completed is False
    assert result.grading_requests == []
    mapper.assert_called_once_with(error, event="security_scanning.repo_file_error")
    read.assert_not_awaited()


@pytest.mark.asyncio
async def test_later_incomplete_step_discards_previously_recorded_grading(monkeypatch):
    job, paths = _evidence_flow(monkeypatch)
    workflow = engine_module.workflow_for(job.requirement.submission_type)
    assert workflow is not None
    monkeypatch.setattr(
        engine_module,
        "workflow_for",
        lambda _: replace(
            workflow,
            steps=(
                *workflow.steps,
                _step(security_checks.check_codeql_status, "later-gate"),
            ),
        ),
    )
    incomplete = github_errors.github_error_to_result(
        httpx.ConnectError("connection details"), event="test.upstream_error"
    )
    gate = AsyncMock(
        side_effect=[
            ValidationResult(is_valid=True, message="Initial gate passed."),
            incomplete,
        ]
    )
    monkeypatch.setattr(security_checks, "verify_codeql_status", gate)
    build_prompt = Mock()
    monkeypatch.setattr(engine_module, "build_repo_rubric_message", build_prompt)

    result = await run_verification(
        job, repo_files=InMemoryRepoFiles(dict.fromkeys(paths, "evidence"))
    )

    assert gate.await_count == 2
    assert result.validation_result.verification_completed is False
    assert result.validation_result.message == incomplete.message
    assert result.grading_requests == []
    build_prompt.assert_not_called()


async def test_repository_rubric_blocks_oversized_evidence(monkeypatch):
    job, paths = _evidence_flow(monkeypatch)
    files = dict.fromkeys(paths, "complete")
    files[paths[0]] = "x" * (51 * 1024)
    result = await run_verification(job, repo_files=InMemoryRepoFiles(files))
    assert result.validation_result.error_code == "evidence.item_limit"
    assert not result.validation_result.is_valid
    assert not result.validation_result.verification_completed
    assert result.grading_requests == []


async def test_oversized_reflection_is_incomplete_without_any_repository_read():
    repo = AsyncMock()
    result = await run_verification(
        _career_job("🦊" * (20 * 1024 // 4 + 1)),
        repo_files=repo,
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
    result = await run_verification(job, repo_files=InMemoryRepoFiles(files))
    assert result.validation_result.is_valid
    assert len(result.grading_requests) == 1
    prompt = json.loads(result.grading_requests[0].message.split("\n\n", 1)[1])
    assert prompt["evidence"]["optional_presence"] == dict.fromkeys(
        task.evidence.optional_files,
        False,
    )


@pytest.mark.parametrize("completed", [False, True])
async def test_any_later_failed_gate_discards_earlier_grading(monkeypatch, completed):
    job, paths = _evidence_flow(monkeypatch)
    workflow = engine_module.workflow_for(job.requirement.submission_type)
    monkeypatch.setattr(
        engine_module,
        "workflow_for",
        lambda _: replace(
            workflow,
            steps=(
                *workflow.steps,
                _step(security_checks.check_codeql_status, "later-gate"),
            ),
        ),
    )
    code = "evidence.required_missing" if completed else "evidence.total_limit"
    monkeypatch.setattr(
        security_checks,
        "verify_codeql_status",
        AsyncMock(
            side_effect=[
                ValidationResult(is_valid=True, message="First gate passed"),
                ValidationResult(
                    is_valid=False,
                    message="Later gate blocked",
                    error_code=code,
                    verification_completed=completed,
                ),
            ]
        ),
    )
    build = Mock()
    monkeypatch.setattr(engine_module, "build_repo_rubric_message", build)
    result = await run_verification(
        job,
        repo_files=InMemoryRepoFiles(dict.fromkeys(paths, "full evidence")),
    )
    assert result.validation_result.error_code == code
    assert result.validation_result.verification_completed == completed
    assert result.grading_requests == []
    build.assert_not_called()


def test_aggregation_preserves_incomplete_cause_over_later_learner_feedback():
    incomplete = ValidationResult(
        is_valid=False,
        verification_completed=False,
        message="Evidence could not fit",
        error_code="evidence.total_limit",
    )
    missing = ValidationResult(
        is_valid=False,
        message="Missing required work",
        error_code="evidence.required_missing",
    )
    result = engine_module._aggregate(
        [
            StepResult(passed=False, validation_result=incomplete),
            StepResult(passed=False, validation_result=missing),
        ]
    )
    assert not result.verification_completed
    assert result.error_code == incomplete.error_code
    assert result.message == incomplete.message


@pytest.mark.parametrize("mutation", ["truncated", "missing", "wrong_task"])
async def test_engine_rechecks_collector_result_before_recording_grading(
    monkeypatch, mutation
):
    from learn_to_cloud_shared.verification.evidence import apply_evidence_cap

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
        career_checks, "collect_submitted_text_evidence", lambda *_: bundle
    )
    result = await run_verification(job)
    assert result.validation_result.error_code == "evidence.selection"
    assert not result.validation_result.verification_completed
    assert result.grading_requests == []


@pytest.mark.parametrize(
    "check",
    [
        partial(
            security_checks.check_security_scanning_review,
            task=SECURITY_SCANNING_RUBRIC_TASK,
        ),
    ],
)
async def test_missing_rubric_repository_is_explicit_incomplete_configuration(check):
    job = _job()
    result = await engine_module._run_step(
        _step(check, "rubric"),
        StepContext(job=job, repository=None, submitted_value=job.submitted_value),
    )
    assert not result.passed
    assert result.validation_result.error_code == "evidence.configuration"
    assert not result.validation_result.verification_completed
    assert result.grading_task is None


@pytest.mark.asyncio
async def test_career_workflow_prepares_text_grading_in_one_step(monkeypatch):
    from learn_to_cloud_shared.verification.tasks.phase7 import (
        CAREER_REFLECTION_RUBRIC_TASK,
    )

    text = "A specific, first-person reflection on my target role and projects."
    workflow = workflows_module.workflow_for(SubmissionType.CAREER_REFLECTION)
    assert len(workflow.steps) == 1
    assert workflow.steps[0].name == "career_reflection"
    tracer = _Tracer()
    monkeypatch.setattr(engine_module, "_tracer", tracer)
    result = await run_verification(_career_job(text))

    assert result.validation_result.is_valid is True
    assert result.validation_result.message == (
        "Reflection received. Reviewing your answers."
    )
    assert result.grading_requests is not None
    assert len(result.grading_requests) == 1
    request = result.grading_requests[0]
    assert request.task.id == CAREER_REFLECTION_RUBRIC_TASK.id
    assert request.task.evidence.source == "submitted_text"
    assert text in request.message
    assert len(tracer.spans) == 1
    assert tracer.spans[0][1].attributes == {
        "verification.check.name": "career_reflection",
        "verification.task.id": CAREER_REFLECTION_RUBRIC_TASK.id,
        "verification.step.result": "passed",
    }


# ---------------------------------------------------------------------------
# Phase 0-2 gate-only workflows: profile README, repo fork, CTF and networking
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


@pytest.mark.asyncio
async def test_profile_readme_workflow_passes_through_validator(monkeypatch):
    from learn_to_cloud_shared_test_support.requirement_factories import (
        profile_readme_requirement,
    )

    sentinel = ValidationResult(is_valid=True, message="Profile README validated")

    validate = AsyncMock(return_value=sentinel)
    monkeypatch.setattr(github_checks, "validate_profile_readme", validate)

    job = _phase02_job(
        profile_readme_requirement(),
        "https://github.com/learner/learner",
    )
    result = await run_verification(job)

    validate.assert_awaited_once_with(job.target)
    assert result.validation_result is sentinel
    assert result.grading_requests == []


@pytest.mark.asyncio
async def test_repo_fork_workflow_passes_through_validator(monkeypatch):
    sentinel = ValidationResult(is_valid=True, message="Repository fork validated")

    validate = AsyncMock(return_value=sentinel)
    monkeypatch.setattr(github_checks, "validate_repo_fork", validate)

    job = _phase02_job(
        repo_fork_requirement(),
        "https://github.com/learner/test-repo",
    )
    result = await run_verification(job)

    validate.assert_awaited_once_with(job.target)
    assert result.validation_result is sentinel
    assert result.grading_requests == []


@pytest.mark.asyncio
async def test_ctf_token_workflow_passes_through_validator(monkeypatch):
    from learn_to_cloud_shared_test_support.requirement_factories import (
        ctf_token_requirement,
    )

    captured: dict[str, str] = {}

    def fake_ctf(token, username):
        captured["token"] = token
        captured["username"] = username
        return ValidationResult(is_valid=True, message="CTF token valid")

    monkeypatch.setattr(tokens_checks, "verify_ctf_token", fake_ctf)

    job = _phase02_job(ctf_token_requirement(), "the-token")
    result = await run_verification(job)

    assert result.validation_result.is_valid is True
    assert result.grading_requests == []
    assert captured == {"token": "the-token", "username": "learner"}


@pytest.mark.asyncio
async def test_networking_token_workflow_passes_through_validator(monkeypatch):
    from learn_to_cloud_shared_test_support.requirement_factories import (
        networking_token_requirement,
    )

    sentinel = ValidationResult(is_valid=False, message="Networking token invalid")
    verify = Mock(return_value=sentinel)
    monkeypatch.setattr(tokens_checks, "verify_networking_token", verify)

    job = _phase02_job(networking_token_requirement(), "bad-token")
    result = await run_verification(job)

    verify.assert_called_once_with("bad-token", "learner")
    assert result.validation_result is sentinel
    assert result.grading_requests == []


@pytest.mark.asyncio
async def test_workflow_requiring_username_short_circuits_when_missing():
    from learn_to_cloud_shared_test_support.requirement_factories import (
        ctf_token_requirement,
    )

    job = _phase02_job(ctf_token_requirement(), "the-token", github_username=None)
    result = await run_verification(job)

    assert result.validation_result.is_valid is False
    assert result.validation_result.username_match is False
    assert "GitHub username is required" in result.validation_result.message
    assert result.grading_requests == []


# ---------------------------------------------------------------------------
# Registry exhaustiveness: every submission type must resolve to a workflow so
# no type silently falls through to an "unknown submission type" error.
# ---------------------------------------------------------------------------


def test_every_submission_type_has_a_registered_workflow():
    from learn_to_cloud_shared.models import SubmissionType
    from learn_to_cloud_shared.verification.workflows import workflow_for

    missing = [t for t in SubmissionType if workflow_for(t) is None]

    assert missing == [], f"submission types without a workflow: {missing}"


# ---------------------------------------------------------------------------
# Every workflow step must reference a check directly.
# ---------------------------------------------------------------------------


def test_every_registered_workflow_step_is_valid():
    from learn_to_cloud_shared.verification.workflows import _WORKFLOW_REGISTRY

    for submission_type, workflow in _WORKFLOW_REGISTRY.items():
        for step in workflow.steps:
            assert callable(step.check), submission_type
