"""Tests for the declarative verification engine."""

import json
from dataclasses import replace
from unittest.mock import AsyncMock, Mock
from uuid import uuid4

import httpx
import pytest
from opentelemetry.trace import Status, StatusCode

from learn_to_cloud_shared.models import SubmissionType
from learn_to_cloud_shared.schemas import TaskResult, ValidationResult
from learn_to_cloud_shared.submission_values import submitted_value_from_raw
from learn_to_cloud_shared.testing.requirement_factories import (
    make_requirement,
    repo_fork_requirement,
)
from learn_to_cloud_shared.verification import engine as engine_module
from learn_to_cloud_shared.verification import github_errors
from learn_to_cloud_shared.verification import repo_files as repo_files_module
from learn_to_cloud_shared.verification.deployed_api import DeployedApiServerError
from learn_to_cloud_shared.verification.engine import (
    CheckParams,
    CIStatusParams,
    Step,
    StepContext,
    StepResult,
    VerificationProfile,
    check_for,
    register_check,
    run_verification,
)
from learn_to_cloud_shared.verification.repo_files import (
    GitHubRepoFiles,
    InMemoryRepoFiles,
)
from learn_to_cloud_shared.verification.tasks.base import (
    EvidenceBundle,
    EvidenceItem,
)
from learn_to_cloud_shared.verification_workflow import (
    GradingDisposition,
    PreparedVerificationAttempt,
)
from tests.fakes.github_metadata import InMemoryGitHubMetadata


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


class PassingCheckParams(CheckParams):
    check_name = "test_gate_pass"


class HardFailParams(CheckParams):
    check_name = "hard_fail"


class NeverRunsParams(CheckParams):
    check_name = "never_runs"


class SoftFailParams(CheckParams):
    check_name = "soft_fail"


class AfterSoftParams(CheckParams):
    check_name = "after_soft"


class EmitEvidenceParams(CheckParams):
    check_name = "emit_evidence"


class ReadEvidenceParams(CheckParams):
    check_name = "read_evidence"


class UnknownCheckParams(CheckParams):
    check_name = "does-not-exist"


class ExplodingCheckParams(CheckParams):
    check_name = "exploding"


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


def _step(params: CheckParams, task_id: str) -> Step:
    return Step(params=params, task_id=task_id)


def _profile(*steps: Step) -> VerificationProfile:
    return VerificationProfile(requires_username=False, steps=steps)


@pytest.mark.asyncio
async def test_run_verification_uses_declared_steps(monkeypatch):
    bundle = EvidenceBundle(
        task_id="gate",
        source="repo_files",
        items=[EvidenceItem(path="a.txt", content="x")],
    )

    @register_check(PassingCheckParams)
    async def _gate(context: StepContext, params) -> StepResult:
        return StepResult(
            passed=True,
            task_result=TaskResult(task_name="Gate", passed=True, feedback="ok"),
            evidence=[bundle],
        )

    monkeypatch.setattr(
        engine_module,
        "profile_for",
        lambda _t: _profile(_step(PassingCheckParams(), "gate")),
    )
    tracer = _Tracer()
    monkeypatch.setattr(engine_module, "_tracer", tracer)

    result = await run_verification(_job())

    assert result.validation_result.is_valid is True
    assert result.validation_result.task_results == [
        TaskResult(task_name="Gate", passed=True, feedback="ok")
    ]
    assert result.evidence == [bundle]
    assert len(tracer.spans) == 2
    _, ownership_span, _ = tracer.spans[0]
    assert ownership_span.attributes == {
        "verification.check.name": "github_repository_ownership",
        "verification.step.result": "passed",
    }
    name, span, options = tracer.spans[-1]
    assert name == "verification.step"
    assert span.attributes == {
        "verification.check.name": "test_gate_pass",
        "verification.task.id": "gate",
        "verification.step.result": "passed",
    }
    assert options["record_exception"] is False
    assert options["set_status_on_exception"] is False


@pytest.mark.asyncio
async def test_step_span_records_error_type_without_exception_details(monkeypatch):
    @register_check(ExplodingCheckParams)
    async def _explode(context: StepContext, params) -> StepResult:
        raise RuntimeError("sensitive failure details")

    monkeypatch.setattr(
        engine_module,
        "profile_for",
        lambda _t: _profile(_step(ExplodingCheckParams(), "explode")),
    )
    tracer = _Tracer()
    monkeypatch.setattr(engine_module, "_tracer", tracer)

    with pytest.raises(RuntimeError, match="sensitive failure details"):
        await run_verification(_job())

    _, span, _ = tracer.spans[-1]
    assert span.attributes == {
        "verification.check.name": "exploding",
        "verification.task.id": "explode",
        "verification.step.result": "error",
        "error.type": "RuntimeError",
    }
    assert span.status is not None
    assert span.status.status_code is StatusCode.ERROR


@pytest.mark.asyncio
async def test_failed_gate_short_circuits(monkeypatch):
    ran: list[str] = []

    @register_check(HardFailParams)
    async def _first(context: StepContext, params) -> StepResult:
        ran.append("first")
        return StepResult(passed=False, stop_on_fail=True)

    @register_check(NeverRunsParams)
    async def _second(context: StepContext, params) -> StepResult:
        ran.append("second")
        return StepResult(passed=True)

    monkeypatch.setattr(
        engine_module,
        "profile_for",
        lambda _t: _profile(
            _step(HardFailParams(), "a"),
            _step(NeverRunsParams(), "b"),
        ),
    )

    result = await run_verification(_job())

    assert ran == ["first"]
    assert result.validation_result.is_valid is False


@pytest.mark.asyncio
async def test_stop_on_fail_false_continues(monkeypatch):
    ran: list[str] = []

    @register_check(SoftFailParams)
    async def _soft(context: StepContext, params) -> StepResult:
        ran.append("soft")
        return StepResult(passed=False, stop_on_fail=False)

    @register_check(AfterSoftParams)
    async def _after(context: StepContext, params) -> StepResult:
        ran.append("after")
        return StepResult(passed=True)

    monkeypatch.setattr(
        engine_module,
        "profile_for",
        lambda _t: _profile(
            _step(SoftFailParams(), "a"),
            _step(AfterSoftParams(), "b"),
        ),
    )

    result = await run_verification(_job())

    assert ran == ["soft", "after"]
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
async def test_later_step_sees_prior_evidence(monkeypatch):
    seen: list[int] = []
    bundle = EvidenceBundle(task_id="a", source="repo_files")

    @register_check(EmitEvidenceParams)
    async def _emit(context: StepContext, params) -> StepResult:
        return StepResult(passed=True, evidence=[bundle])

    @register_check(ReadEvidenceParams)
    async def _read(context: StepContext, params) -> StepResult:
        seen.append(len(context.evidence_so_far))
        return StepResult(passed=True)

    monkeypatch.setattr(
        engine_module,
        "profile_for",
        lambda _t: _profile(
            _step(EmitEvidenceParams(), "a"),
            _step(ReadEvidenceParams(), "b"),
        ),
    )

    await run_verification(_job())

    assert seen == [1]


@pytest.mark.asyncio
async def test_unregistered_type_returns_unknown_result(monkeypatch):
    monkeypatch.setattr(engine_module, "profile_for", lambda _t: None)

    result = await run_verification(_job())

    assert result.validation_result.is_valid is False
    assert "Unknown submission type" in result.validation_result.message
    assert result.grading_requests == []
    assert (
        result.grading_disposition == GradingDisposition.SKIPPED_UNKNOWN_SUBMISSION_TYPE
    )


def test_register_check_rejects_duplicates():
    with pytest.raises(ValueError, match="already registered"):

        @register_check(CIStatusParams)
        async def _dupe(context, params):  # pragma: no cover - registration fails
            return StepResult(passed=True)


def test_check_for_unknown_raises():
    with pytest.raises(KeyError):
        check_for(UnknownCheckParams())


_REPOSITORY_TYPES = {
    SubmissionType.PROFILE_README,
    SubmissionType.REPO_FORK,
    SubmissionType.JOURNAL_API_VERIFIER,
    SubmissionType.DEPLOYMENT_ARCHITECTURE,
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
    assert result.evidence is None
    assert result.grading_disposition == (
        GradingDisposition.NOT_REQUIRED
        if submission_type
        in {
            SubmissionType.PROFILE_README,
            SubmissionType.REPO_FORK,
            SubmissionType.CTF_TOKEN,
            SubmissionType.NETWORKING_TOKEN,
            SubmissionType.DEPLOYED_API,
        }
        else GradingDisposition.SKIPPED_GATE_FAILED
    )


@pytest.mark.asyncio
async def test_canonical_repository_reaches_ci_evidence_and_prompt(
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
    monkeypatch.setattr(engine_module, "verify_ci_status", ci)
    files = AsyncMock(spec=RepoFiles)
    files.file.return_value = "synthetic evidence"
    job = _journal_job()

    result = await run_verification(job, repo_files=files)

    lookup.assert_awaited_once_with("learner", "journal-starter")
    ci.assert_awaited_once_with("new-name", "moved-repo")
    assert files.file.await_count > 0
    assert all(
        call.args[:2] == ("new-name", "moved-repo")
        for call in files.file.await_args_list
    )
    assert result.grading_requests
    prompt = json.loads(result.grading_requests[0].message.split("\n\n", 1)[1])
    assert prompt["repository"] == {"owner": "new-name", "name": "moved-repo"}
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


# ---------------------------------------------------------------------------
# Phase 3 journal API profile: CI gate + rubric review + grading requests.
# ---------------------------------------------------------------------------


def _journal_job() -> PreparedVerificationAttempt:
    from learn_to_cloud_shared.testing.requirement_factories import (
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
async def test_journal_profile_records_grading_requests_when_ci_passes(monkeypatch):
    from learn_to_cloud_shared.verification.repo_files import InMemoryRepoFiles
    from learn_to_cloud_shared.verification.tasks.phase3 import (
        JOURNAL_API_FINAL_RUBRIC_TASK,
        JOURNAL_API_IMPORTANT_PATHS,
    )

    async def fake_ci(owner, repo, runs=None):
        return ValidationResult(is_valid=True, message="CI is green")

    monkeypatch.setattr(engine_module, "verify_ci_status", fake_ci)
    repo_files = InMemoryRepoFiles(
        {path: f"content of {path}" for path in JOURNAL_API_IMPORTANT_PATHS}
    )

    result = await run_verification(_journal_job(), repo_files=repo_files)

    assert result.validation_result.is_valid is True
    assert result.evidence is not None and len(result.evidence) == 1
    assert result.grading_requests is not None
    assert len(result.grading_requests) == 1
    assert result.grading_disposition == GradingDisposition.REQUESTED
    request = result.grading_requests[0]
    assert request.task.id == JOURNAL_API_FINAL_RUBRIC_TASK.id
    assert "journal-api-implementation" in request.message


@pytest.mark.asyncio
async def test_journal_profile_skips_grading_when_ci_fails(monkeypatch):
    from learn_to_cloud_shared.verification.repo_files import InMemoryRepoFiles

    async def fake_ci(owner, repo, runs=None):
        return ValidationResult(is_valid=False, message="CI is red")

    monkeypatch.setattr(engine_module, "verify_ci_status", fake_ci)

    result = await run_verification(_journal_job(), repo_files=InMemoryRepoFiles({}))

    assert result.validation_result.is_valid is False
    assert result.validation_result.message == "CI is red"
    assert result.grading_requests == []
    assert result.grading_disposition == GradingDisposition.SKIPPED_GATE_FAILED
    assert result.evidence is None


# ---------------------------------------------------------------------------
# Phase 4 deployment architecture profile: gate + deploy.sh/description rubric.
# ---------------------------------------------------------------------------


def _deployment_job(description: str) -> PreparedVerificationAttempt:
    from learn_to_cloud_shared.testing.requirement_factories import (
        deployment_architecture_requirement,
    )

    requirement = deployment_architecture_requirement(
        slug="deployment-architecture",
        required_repo="owner/journal-starter",
    )
    return PreparedVerificationAttempt(
        id=uuid4(),
        user_id=1,
        github_username="learner",
        requirement=requirement,
        submitted_value=submitted_value_from_raw(requirement, description),
    )


@pytest.mark.asyncio
async def test_deployment_profile_bundles_script_and_description():
    from learn_to_cloud_shared.verification.repo_files import InMemoryRepoFiles
    from learn_to_cloud_shared.verification.tasks.phase4 import (
        DEPLOYMENT_ARCHITECTURE_RUBRIC_TASK,
    )

    description = (
        "My two-tier deployment provisions a public API tier and a private "
        "database tier in an isolated subnet, all created idempotently by "
        "deploy.sh with restricted inbound rules and TLS termination for the "
        "API. Traffic flows from the internet to the load balancer, then to "
        "the API compute, and only the API can reach the private database."
    )
    repo_files = InMemoryRepoFiles({"deploy.sh": "#!/bin/bash\naz group create\n"})

    result = await run_verification(_deployment_job(description), repo_files=repo_files)

    assert result.validation_result.is_valid is True
    assert result.grading_requests is not None
    assert len(result.grading_requests) == 1
    request = result.grading_requests[0]
    assert request.task.id == DEPLOYMENT_ARCHITECTURE_RUBRIC_TASK.id
    assert "deploy.sh" in request.message
    assert description in request.message


@pytest.mark.asyncio
async def test_deployment_profile_gate_fails_when_description_too_short():
    from learn_to_cloud_shared.verification.repo_files import InMemoryRepoFiles

    repo_files = InMemoryRepoFiles({"deploy.sh": "#!/bin/bash\n"})

    result = await run_verification(_deployment_job("too short"), repo_files=repo_files)

    assert result.validation_result.is_valid is False
    assert result.grading_requests == []
    assert result.evidence is None


@pytest.mark.asyncio
async def test_deployment_profile_gate_fails_when_deploy_script_missing():
    from learn_to_cloud_shared.verification.repo_files import InMemoryRepoFiles

    description = (
        "My two-tier deployment provisions a public API tier and a private "
        "database tier in an isolated subnet, all created idempotently by a "
        "script with restricted inbound rules and TLS termination for the "
        "API. Traffic flows from the internet to the load balancer, then to "
        "the API compute, and only the API can reach the private database."
    )
    repo_files = InMemoryRepoFiles({"README.md": "no script here"})

    result = await run_verification(_deployment_job(description), repo_files=repo_files)

    assert result.validation_result.is_valid is False
    assert result.grading_requests == []


# ---------------------------------------------------------------------------
# Phase 4/5 deterministic profiles: deployed API probe and DevOps workflow.
# ---------------------------------------------------------------------------


def _deployed_api_job() -> PreparedVerificationAttempt:
    from learn_to_cloud_shared.testing.requirement_factories import (
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
    from learn_to_cloud_shared.testing.requirement_factories import (
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
async def test_deployed_api_profile_passes_through_deterministic_result(monkeypatch):
    async def fake_validate(base_url):
        assert base_url == "https://api.example.com"
        return ValidationResult(is_valid=True, message="API is healthy")

    monkeypatch.setattr(engine_module, "validate_deployed_api", fake_validate)

    result = await run_verification(_deployed_api_job())

    assert result.validation_result.is_valid is True
    assert result.validation_result.message == "API is healthy"
    assert result.grading_requests == []
    assert result.grading_disposition == GradingDisposition.NOT_REQUIRED
    assert result.evidence is None


@pytest.mark.asyncio
async def test_deployed_api_profile_fails_when_probe_fails(monkeypatch):
    async def fake_validate(base_url):
        return ValidationResult(is_valid=False, message="API unreachable")

    monkeypatch.setattr(engine_module, "validate_deployed_api", fake_validate)

    result = await run_verification(_deployed_api_job())

    assert result.validation_result.is_valid is False
    assert result.grading_requests == []


@pytest.mark.asyncio
async def test_devops_profile_runs_files_then_ghcr_gates(monkeypatch):
    from learn_to_cloud_shared.verification.repo_files import InMemoryRepoFiles

    calls: list[str] = []
    files_task = TaskResult(task_name="Files", passed=True, feedback="present")
    image_task = TaskResult(task_name="Image", passed=True, feedback="pullable")

    async def fake_files(owner, repo, repo_files=None):
        calls.append("files")
        assert owner == "learner"
        assert repo == "devops-repo"
        return ValidationResult(
            is_valid=True,
            message="Required files exist",
            task_results=[files_task],
        )

    async def fake_image(owner):
        calls.append("image")
        assert owner == "learner"
        return ValidationResult(
            is_valid=True,
            message="Container image is pullable",
            task_results=[image_task],
        )

    monkeypatch.setattr(engine_module, "verify_required_devops_files", fake_files)
    monkeypatch.setattr(engine_module, "verify_public_ghcr_image", fake_image)

    repo_files = InMemoryRepoFiles(
        {
            "Dockerfile": "FROM python:3.12-slim",
            ".github/workflows/deploy.yml": "jobs: {}",
            "infra/main.tf": 'resource "azurerm_kubernetes_cluster" "main" {}',
            "k8s/deployment.yaml": "kind: Deployment",
            "k8s/service.yaml": "kind: Service",
        }
    )
    result = await run_verification(_devops_job(), repo_files=repo_files)

    assert calls == ["files", "image"]
    assert result.validation_result.is_valid is True
    assert result.validation_result.message == "Container image is pullable"
    assert result.validation_result.task_results == [files_task, image_task]
    assert result.grading_requests is not None
    assert len(result.grading_requests) == 1
    assert result.grading_disposition == GradingDisposition.REQUESTED
    assert result.evidence is not None
    assert [item.path for item in result.evidence[0].items] == [
        "Dockerfile",
        "k8s/deployment.yaml",
        "k8s/service.yaml",
        ".github/workflows/deploy.yml",
        "infra/main.tf",
    ]
    request = result.grading_requests[0]
    assert request.task.id == "devops-implementation-rubric"
    assert ".github/workflows/deploy.yml" in request.message
    assert "infra/main.tf" in request.message


@pytest.mark.asyncio
async def test_devops_profile_skips_ghcr_when_files_gate_fails(monkeypatch):
    calls: list[str] = []

    async def fake_files(owner, repo, repo_files=None):
        calls.append("files")
        return ValidationResult(is_valid=False, message="Missing workflow file")

    async def fake_image(owner):
        calls.append("image")
        return ValidationResult(is_valid=True, message="unexpected")

    monkeypatch.setattr(engine_module, "verify_required_devops_files", fake_files)
    monkeypatch.setattr(engine_module, "verify_public_ghcr_image", fake_image)

    result = await run_verification(_devops_job())

    assert calls == ["files"]
    assert result.validation_result.is_valid is False
    assert result.validation_result.message == "Missing workflow file"
    assert result.grading_requests == []
    assert result.grading_disposition == GradingDisposition.SKIPPED_GATE_FAILED


@pytest.mark.asyncio
async def test_devops_profile_stops_when_ghcr_gate_fails(monkeypatch):
    async def fake_files(owner, repo, repo_files=None):
        return ValidationResult(is_valid=True, message="Required files exist")

    async def fake_image(owner):
        return ValidationResult(is_valid=False, message="Image is private")

    monkeypatch.setattr(engine_module, "verify_required_devops_files", fake_files)
    monkeypatch.setattr(engine_module, "verify_public_ghcr_image", fake_image)

    result = await run_verification(_devops_job())

    assert result.validation_result.is_valid is False
    assert result.validation_result.message == "Image is private"
    assert result.grading_requests == []
    assert result.grading_disposition == GradingDisposition.SKIPPED_GATE_FAILED


# ---------------------------------------------------------------------------
# Phase 6/7 rubric profiles: security scanning (repo) and career reflection
# (text-only) both gate then record a grading request.
# ---------------------------------------------------------------------------


def _security_job() -> PreparedVerificationAttempt:
    from learn_to_cloud_shared.testing.requirement_factories import (
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
    from learn_to_cloud_shared.testing.requirement_factories import (
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
async def test_security_profile_records_grading_request_when_gate_passes(monkeypatch):
    from learn_to_cloud_shared.verification.repo_files import InMemoryRepoFiles
    from learn_to_cloud_shared.verification.tasks.phase6 import (
        SECURITY_SCANNING_RUBRIC_TASK,
    )

    async def fake_gate(owner, repo):
        return ValidationResult(is_valid=True, message="CodeQL green on main")

    monkeypatch.setattr(engine_module, "verify_codeql_status", fake_gate)
    repo_files = InMemoryRepoFiles(
        {".github/workflows/codeql.yml": "name: CodeQL\non: [push]\n"}
    )

    result = await run_verification(_security_job(), repo_files=repo_files)

    assert result.validation_result.is_valid is True
    assert result.grading_requests is not None
    assert len(result.grading_requests) == 1
    assert result.grading_requests[0].task.id == SECURITY_SCANNING_RUBRIC_TASK.id


@pytest.mark.asyncio
async def test_security_profile_skips_grading_when_gate_fails(monkeypatch):
    from learn_to_cloud_shared.verification.repo_files import InMemoryRepoFiles

    async def fake_gate(owner, repo):
        return ValidationResult(is_valid=False, message="No CodeQL runs found")

    monkeypatch.setattr(engine_module, "verify_codeql_status", fake_gate)

    result = await run_verification(_security_job(), repo_files=InMemoryRepoFiles({}))

    assert result.validation_result.is_valid is False
    assert result.grading_requests == []
    assert result.evidence is None


def _evidence_flow(flow, monkeypatch):
    passing = ValidationResult(is_valid=True, message="Prerequisite passed.")
    monkeypatch.setattr(
        engine_module, "verify_ci_status", AsyncMock(return_value=passing)
    )
    monkeypatch.setattr(
        engine_module, "verify_codeql_status", AsyncMock(return_value=passing)
    )
    monkeypatch.setattr(
        engine_module, "verify_public_ghcr_image", AsyncMock(return_value=passing)
    )
    if flow == "exact":
        from learn_to_cloud_shared.verification.tasks.phase3 import (
            JOURNAL_API_IMPORTANT_PATHS,
        )

        return _journal_job(), list(JOURNAL_API_IMPORTANT_PATHS)
    if flow == "discovered":
        return _devops_job(), [
            "Dockerfile",
            "k8s/deployment.yaml",
            "k8s/service.yaml",
            ".github/workflows/deploy.yml",
            "infra/main.tf",
        ]
    if flow == "security":
        from learn_to_cloud_shared.verification.security_scanning import (
            SECURITY_SCANNING_EVIDENCE_PATHS,
        )

        return _security_job(), SECURITY_SCANNING_EVIDENCE_PATHS
    return _deployment_job("A detailed architecture description. " * 10), ["deploy.sh"]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("flow", "event"),
    [
        ("exact", "llm_rubric_review.repo_file_error"),
        ("discovered", "llm_rubric_review.repo_file_error"),
        ("security", "security_scanning.repo_file_error"),
        ("deployment", "deployment_architecture.repo_file_error"),
    ],
)
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
async def test_failed_evidence_read_stops_grading(
    monkeypatch, flow, event, failure, category
):
    job, paths = _evidence_flow(flow, monkeypatch)
    failed_path = paths[0] if flow == "deployment" else paths[1]
    fetched = []
    mapper = Mock(wraps=github_errors.github_error_to_result)
    monkeypatch.setattr(engine_module, "github_error_to_result", mapper)
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

    assert fetched == paths[: 1 if flow == "deployment" else 2]
    assert result.validation_result.is_valid is False
    assert result.validation_result.verification_completed is False
    assert "private" not in result.validation_result.message
    assert result.evidence is None
    assert result.grading_requests == []
    assert result.grading_disposition is GradingDisposition.SKIPPED_GATE_FAILED
    mapper.assert_called_once()
    assert mapper.call_args.kwargs == {"event": event}
    counter.add.assert_called_once_with(1, {"error.type": category})
    assert tracer.spans[0][1].attributes["verification.step.result"] == "passed"
    assert tracer.spans[-1][1].attributes["verification.step.result"] == "unavailable"
    assert tracer.spans[-1][1].status.status_code is StatusCode.ERROR


@pytest.mark.asyncio
@pytest.mark.parametrize("flow", ["exact", "discovered", "security", "deployment"])
@pytest.mark.parametrize(
    "error",
    [
        RuntimeError("programming bug"),
        DeployedApiServerError("another integration", status_code=503),
    ],
)
async def test_evidence_boundaries_do_not_swallow_unsupported_errors(
    monkeypatch, flow, error
):
    job, paths = _evidence_flow(flow, monkeypatch)
    files = InMemoryRepoFiles(dict.fromkeys(paths, "evidence"))
    monkeypatch.setattr(files, "file", AsyncMock(side_effect=error))
    mapper = Mock(wraps=github_errors.github_error_to_result)
    monkeypatch.setattr(engine_module, "github_error_to_result", mapper)

    with pytest.raises(type(error)) as raised:
        await run_verification(job, repo_files=files)

    assert raised.value is error
    mapper.assert_not_called()


@pytest.mark.asyncio
@pytest.mark.parametrize("flow", ["exact", "discovered", "security", "deployment"])
async def test_missing_optional_evidence_preserves_existing_grading(monkeypatch, flow):
    job, paths = _evidence_flow(flow, monkeypatch)
    contents = dict.fromkeys(paths, "evidence")
    missing_path = paths[0] if flow == "deployment" else paths[1]
    del contents[missing_path]
    files = InMemoryRepoFiles(contents, tree=paths)

    result = await run_verification(job, repo_files=files)

    assert result.validation_result.verification_completed is True
    assert result.grading_disposition is GradingDisposition.REQUESTED
    assert result.grading_requests
    assert missing_path not in [item.path for item in result.evidence[0].items]


@pytest.mark.asyncio
@pytest.mark.parametrize("flow", ["discovered", "deployment"])
@pytest.mark.parametrize(
    "error",
    [
        github_errors.GitHubServerError("Unavailable", status_code=503),
        httpx.ConnectError("private connection details"),
    ],
)
async def test_tree_failure_stops_grading_with_tree_event(monkeypatch, flow, error):
    job, _ = _evidence_flow(flow, monkeypatch)
    monkeypatch.setattr(
        engine_module,
        "verify_required_devops_files",
        AsyncMock(return_value=ValidationResult(is_valid=True, message="Files found.")),
    )
    mapper = Mock(wraps=github_errors.github_error_to_result)
    monkeypatch.setattr(engine_module, "github_error_to_result", mapper)
    monkeypatch.setattr(
        "learn_to_cloud_shared.verification.deployment_architecture.github_error_to_result",
        mapper,
    )
    files = InMemoryRepoFiles(tree_error=error)
    read = AsyncMock()
    monkeypatch.setattr(files, "file", read)

    result = await run_verification(job, repo_files=files)

    assert result.validation_result.verification_completed is False
    assert result.grading_requests == []
    assert result.evidence is None
    assert result.grading_disposition is GradingDisposition.SKIPPED_GATE_FAILED
    event = (
        "llm_rubric_review.repo_tree_error"
        if flow == "discovered"
        else "deployment_architecture.repo_tree_error"
    )
    mapper.assert_called_once_with(error, event=event)
    read.assert_not_awaited()


@pytest.mark.asyncio
async def test_later_incomplete_step_discards_previously_recorded_grading(monkeypatch):
    job, paths = _evidence_flow("exact", monkeypatch)
    profile = engine_module.profile_for(job.requirement.submission_type)
    assert profile is not None
    monkeypatch.setattr(
        engine_module,
        "profile_for",
        lambda _: replace(
            profile, steps=(*profile.steps, _step(CIStatusParams(), "later-gate"))
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
    monkeypatch.setattr(engine_module, "verify_ci_status", gate)
    build_prompt = Mock()
    monkeypatch.setattr(engine_module, "build_repo_rubric_message", build_prompt)

    result = await run_verification(
        job, repo_files=InMemoryRepoFiles(dict.fromkeys(paths, "evidence"))
    )

    assert gate.await_count == 2
    assert result.evidence
    assert result.validation_result.verification_completed is False
    assert result.validation_result.message == incomplete.message
    assert result.grading_requests == []
    assert result.grading_disposition is GradingDisposition.SKIPPED_GATE_FAILED
    build_prompt.assert_not_called()


@pytest.mark.asyncio
async def test_career_profile_records_text_grading_request_when_gate_passes():
    from learn_to_cloud_shared.verification.tasks.phase7 import (
        CAREER_REFLECTION_RUBRIC_TASK,
    )

    text = "A specific, first-person reflection on my target role and projects."
    result = await run_verification(_career_job(text))

    assert result.validation_result.is_valid is True
    assert result.grading_requests is not None
    assert len(result.grading_requests) == 1
    request = result.grading_requests[0]
    assert request.task.id == CAREER_REFLECTION_RUBRIC_TASK.id
    assert request.task.evidence.source == "submitted_text"
    assert text in request.message


@pytest.mark.asyncio
async def test_career_profile_skips_grading_when_gate_fails(monkeypatch):
    def fake_gate(text):
        return ValidationResult(is_valid=False, message="Your reflection was empty.")

    monkeypatch.setattr(engine_module, "validate_career_reflection", fake_gate)
    text = "A specific, first-person reflection on my target role and projects."

    result = await run_verification(_career_job(text))

    assert result.validation_result.is_valid is False
    assert result.grading_requests == []
    assert result.evidence is None


# ---------------------------------------------------------------------------
# Phase 0-2 gate-only profiles: profile README, repo fork, CTF and networking
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
async def test_profile_readme_profile_passes_through_validator(monkeypatch):
    from learn_to_cloud_shared.testing.requirement_factories import (
        profile_readme_requirement,
    )

    sentinel = ValidationResult(is_valid=True, message="Profile README validated")

    async def fake_readme(target, metadata=None):
        return sentinel

    monkeypatch.setattr(engine_module, "validate_profile_readme", fake_readme)

    job = _phase02_job(
        profile_readme_requirement(),
        "https://github.com/learner/learner",
    )
    result = await run_verification(job)

    assert result.validation_result is sentinel
    assert result.grading_requests == []
    assert result.evidence is None


@pytest.mark.asyncio
async def test_repo_fork_profile_passes_through_validator(monkeypatch):
    sentinel = ValidationResult(is_valid=True, message="Repository fork validated")

    async def fake_fork(target, metadata=None):
        return sentinel

    monkeypatch.setattr(engine_module, "validate_repo_fork", fake_fork)

    job = _phase02_job(
        repo_fork_requirement(),
        "https://github.com/learner/test-repo",
    )
    result = await run_verification(job)

    assert result.validation_result is sentinel
    assert result.grading_requests == []


@pytest.mark.asyncio
async def test_ctf_token_profile_passes_through_validator(monkeypatch):
    from learn_to_cloud_shared.testing.requirement_factories import (
        ctf_token_requirement,
    )

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
async def test_networking_token_profile_passes_through_validator(monkeypatch):
    from learn_to_cloud_shared.testing.requirement_factories import (
        networking_token_requirement,
    )

    def fake_net(token, username):
        return ValidationResult(is_valid=False, message="Networking token invalid")

    monkeypatch.setattr(engine_module, "verify_networking_token", fake_net)

    job = _phase02_job(networking_token_requirement(), "bad-token")
    result = await run_verification(job)

    assert result.validation_result.is_valid is False
    assert result.grading_requests == []


@pytest.mark.asyncio
async def test_profile_requiring_username_short_circuits_when_missing():
    from learn_to_cloud_shared.testing.requirement_factories import (
        ctf_token_requirement,
    )

    job = _phase02_job(ctf_token_requirement(), "the-token", github_username=None)
    result = await run_verification(job)

    assert result.validation_result.is_valid is False
    assert result.validation_result.username_match is False
    assert "GitHub username is required" in result.validation_result.message
    assert result.grading_requests == []
    assert result.grading_disposition == GradingDisposition.SKIPPED_MISSING_USERNAME


# ---------------------------------------------------------------------------
# Registry exhaustiveness: every submission type must resolve to a profile so
# no type silently falls through to an "unknown submission type" error.
# ---------------------------------------------------------------------------


def test_every_submission_type_has_a_registered_profile():
    from learn_to_cloud_shared.models import SubmissionType
    from learn_to_cloud_shared.verification.engine import profile_for

    missing = [t for t in SubmissionType if profile_for(t) is None]

    assert missing == [], f"submission types without a profile: {missing}"


# ---------------------------------------------------------------------------
# Every profile step's params type must own a registered check.
# ---------------------------------------------------------------------------


def test_every_registered_profile_step_is_valid():
    from learn_to_cloud_shared.verification.engine import (
        _CHECK_REGISTRY,
        _PROFILE_REGISTRY,
    )

    for submission_type, profile in _PROFILE_REGISTRY.items():
        for step in profile.steps:
            params_type = type(step.params)
            assert params_type in _CHECK_REGISTRY, (
                f"{submission_type}: check '{params_type.check_name}' is not registered"
            )
