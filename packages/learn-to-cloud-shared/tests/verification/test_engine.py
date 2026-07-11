"""Tests for the declarative verification engine."""

from uuid import uuid4

import pytest

from learn_to_cloud_shared.schemas import TaskResult, ValidationResult
from learn_to_cloud_shared.testing.requirement_factories import (
    repo_fork_requirement,
)
from learn_to_cloud_shared.verification import engine as engine_module
from learn_to_cloud_shared.verification.engine import (
    LegacyValidateParams,
    Step,
    StepContext,
    StepResult,
    VerificationProfile,
    check_for,
    register_check,
    run_profile,
)
from learn_to_cloud_shared.verification.tasks.base import (
    EvidenceBundle,
    EvidenceItem,
)
from learn_to_cloud_shared.verification_job_executor import PreparedVerificationJob


def _job(requirement=None) -> PreparedVerificationJob:
    return PreparedVerificationJob(
        id=uuid4(),
        user_id=1,
        github_username="learner",
        requirement=requirement or repo_fork_requirement(),
        submitted_value="https://github.com/learner/test-repo",
    )


def _step(check: str, task_id: str) -> Step:
    return Step(check=check, params=LegacyValidateParams(), task_id=task_id)


def _profile(*steps: Step) -> VerificationProfile:
    return VerificationProfile(
        adapter=_unused_adapter,
        requires_username=False,
        steps=steps,
    )


async def _unused_adapter(requirement, target, submitted_value, username):
    raise AssertionError("adapter should not be called by the engine")


@pytest.mark.asyncio
async def test_legacy_step_passes_dispatcher_result_through(monkeypatch):
    sentinel = ValidationResult(
        is_valid=True,
        message="dispatcher said so",
        task_results=[TaskResult(task_name="t", passed=True, feedback="f")],
    )

    async def fake_validate(**kwargs):
        return sentinel

    monkeypatch.setattr(engine_module, "validate_submission", fake_validate)
    monkeypatch.setattr(engine_module, "profile_for", lambda _t: None)

    result = await run_profile(_job(repo_fork_requirement()))

    assert result.validation_result is sentinel
    assert result.evidence is None


@pytest.mark.asyncio
async def test_run_profile_uses_declared_steps(monkeypatch):
    bundle = EvidenceBundle(
        task_id="gate",
        source="repo_files",
        items=[EvidenceItem(path="a.txt", content="x")],
    )

    @register_check("test_gate_pass")
    async def _gate(context: StepContext, params) -> StepResult:
        return StepResult(
            passed=True,
            task_result=TaskResult(task_name="Gate", passed=True, feedback="ok"),
            evidence=[bundle],
        )

    monkeypatch.setattr(
        engine_module,
        "descriptor_for",
        lambda _t: _profile(_step("test_gate_pass", "gate")),
    )
    monkeypatch.setattr(engine_module, "profile_for", lambda _t: None)

    result = await run_profile(_job())

    assert result.validation_result.is_valid is True
    assert result.validation_result.task_results == [
        TaskResult(task_name="Gate", passed=True, feedback="ok")
    ]
    assert result.evidence == [bundle]


@pytest.mark.asyncio
async def test_failed_gate_short_circuits(monkeypatch):
    ran: list[str] = []

    @register_check("hard_fail")
    async def _first(context: StepContext, params) -> StepResult:
        ran.append("first")
        return StepResult(passed=False, stop_on_fail=True)

    @register_check("never_runs")
    async def _second(context: StepContext, params) -> StepResult:
        ran.append("second")
        return StepResult(passed=True)

    monkeypatch.setattr(
        engine_module,
        "descriptor_for",
        lambda _t: _profile(_step("hard_fail", "a"), _step("never_runs", "b")),
    )
    monkeypatch.setattr(engine_module, "profile_for", lambda _t: None)

    result = await run_profile(_job())

    assert ran == ["first"]
    assert result.validation_result.is_valid is False


@pytest.mark.asyncio
async def test_stop_on_fail_false_continues(monkeypatch):
    ran: list[str] = []

    @register_check("soft_fail")
    async def _soft(context: StepContext, params) -> StepResult:
        ran.append("soft")
        return StepResult(passed=False, stop_on_fail=False)

    @register_check("after_soft")
    async def _after(context: StepContext, params) -> StepResult:
        ran.append("after")
        return StepResult(passed=True)

    monkeypatch.setattr(
        engine_module,
        "descriptor_for",
        lambda _t: _profile(_step("soft_fail", "a"), _step("after_soft", "b")),
    )
    monkeypatch.setattr(engine_module, "profile_for", lambda _t: None)

    result = await run_profile(_job())

    assert ran == ["soft", "after"]
    assert result.validation_result.is_valid is False


@pytest.mark.asyncio
async def test_later_step_sees_prior_evidence(monkeypatch):
    seen: list[int] = []
    bundle = EvidenceBundle(task_id="a", source="repo_files")

    @register_check("emit_evidence")
    async def _emit(context: StepContext, params) -> StepResult:
        return StepResult(passed=True, evidence=[bundle])

    @register_check("read_evidence")
    async def _read(context: StepContext, params) -> StepResult:
        seen.append(len(context.evidence_so_far))
        return StepResult(passed=True)

    monkeypatch.setattr(
        engine_module,
        "descriptor_for",
        lambda _t: _profile(_step("emit_evidence", "a"), _step("read_evidence", "b")),
    )
    monkeypatch.setattr(engine_module, "profile_for", lambda _t: None)

    await run_profile(_job())

    assert seen == [1]


@pytest.mark.asyncio
async def test_unregistered_descriptor_falls_back_to_legacy(monkeypatch):
    called: dict[str, object] = {}

    async def fake_validate(**kwargs):
        called.update(kwargs)
        return ValidationResult(is_valid=True, message="legacy ran")

    monkeypatch.setattr(engine_module, "validate_submission", fake_validate)
    monkeypatch.setattr(engine_module, "descriptor_for", lambda _t: None)
    monkeypatch.setattr(engine_module, "profile_for", lambda _t: None)

    result = await run_profile(_job())

    assert result.validation_result.message == "legacy ran"
    assert called["expected_username"] == "learner"


def test_register_check_rejects_duplicates():
    with pytest.raises(ValueError, match="already registered"):

        @register_check("legacy_validate")
        async def _dupe(context, params):  # pragma: no cover - registration fails
            return StepResult(passed=True)


def test_check_for_unknown_raises():
    with pytest.raises(KeyError):
        check_for("does-not-exist")


# ---------------------------------------------------------------------------
# Phase 3 journal API profile: CI gate + rubric review + grading requests.
# ---------------------------------------------------------------------------


def _journal_job() -> PreparedVerificationJob:
    from learn_to_cloud_shared.testing.requirement_factories import (
        journal_api_verifier_requirement,
    )

    return PreparedVerificationJob(
        id=uuid4(),
        user_id=1,
        github_username="learner",
        requirement=journal_api_verifier_requirement(
            slug="journal-api-implementation",
            name="Journal API Implementation",
            required_repo="owner/journal-starter",
        ),
        submitted_value="https://github.com/learner/journal-starter",
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

    result = await run_profile(_journal_job(), repo_files=repo_files)

    assert result.validation_result.is_valid is True
    assert result.evidence is not None and len(result.evidence) == 1
    assert result.grading_requests is not None
    assert len(result.grading_requests) == 1
    request = result.grading_requests[0]
    assert request.task.id == JOURNAL_API_FINAL_RUBRIC_TASK.id
    assert "journal-api-implementation" in request.message


@pytest.mark.asyncio
async def test_journal_profile_skips_grading_when_ci_fails(monkeypatch):
    from learn_to_cloud_shared.verification.repo_files import InMemoryRepoFiles

    async def fake_ci(owner, repo, runs=None):
        return ValidationResult(is_valid=False, message="CI is red")

    monkeypatch.setattr(engine_module, "verify_ci_status", fake_ci)

    result = await run_profile(_journal_job(), repo_files=InMemoryRepoFiles({}))

    assert result.validation_result.is_valid is False
    assert result.validation_result.message == "CI is red"
    assert result.grading_requests == []
    assert result.evidence is None


@pytest.mark.asyncio
async def test_legacy_type_leaves_grading_requests_none(monkeypatch):
    async def fake_validate(**kwargs):
        return ValidationResult(is_valid=True, message="legacy ran")

    monkeypatch.setattr(engine_module, "validate_submission", fake_validate)
    monkeypatch.setattr(engine_module, "profile_for", lambda _t: None)

    result = await run_profile(_job(repo_fork_requirement()))

    assert result.grading_requests is None


# ---------------------------------------------------------------------------
# Phase 4 deployment architecture profile: gate + deploy.sh/description rubric.
# ---------------------------------------------------------------------------


def _deployment_job(description: str) -> PreparedVerificationJob:
    from learn_to_cloud_shared.testing.requirement_factories import (
        deployment_architecture_requirement,
    )

    return PreparedVerificationJob(
        id=uuid4(),
        user_id=1,
        github_username="learner",
        requirement=deployment_architecture_requirement(
            slug="deployment-architecture",
            required_repo="owner/journal-starter",
        ),
        submitted_value=description,
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

    result = await run_profile(_deployment_job(description), repo_files=repo_files)

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

    result = await run_profile(_deployment_job("too short"), repo_files=repo_files)

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

    result = await run_profile(_deployment_job(description), repo_files=repo_files)

    assert result.validation_result.is_valid is False
    assert result.grading_requests == []


# ---------------------------------------------------------------------------
# Phase 4/5 deterministic profiles: deployed API probe and DevOps workflow.
# ---------------------------------------------------------------------------


def _deployed_api_job() -> PreparedVerificationJob:
    from learn_to_cloud_shared.testing.requirement_factories import (
        deployed_api_requirement,
    )

    return PreparedVerificationJob(
        id=uuid4(),
        user_id=1,
        github_username=None,
        requirement=deployed_api_requirement(slug="deployed-api"),
        submitted_value="https://api.example.com",
    )


def _devops_job() -> PreparedVerificationJob:
    from learn_to_cloud_shared.testing.requirement_factories import (
        devops_analysis_requirement,
    )

    return PreparedVerificationJob(
        id=uuid4(),
        user_id=1,
        github_username="learner",
        requirement=devops_analysis_requirement(
            slug="devops-analysis",
            required_repo="owner/devops-repo",
        ),
        submitted_value="https://github.com/learner/devops-repo",
    )


@pytest.mark.asyncio
async def test_deployed_api_profile_passes_through_deterministic_result(monkeypatch):
    async def fake_validate(base_url):
        assert base_url == "https://api.example.com"
        return ValidationResult(is_valid=True, message="API is healthy")

    monkeypatch.setattr(engine_module, "validate_deployed_api", fake_validate)

    result = await run_profile(_deployed_api_job())

    assert result.validation_result.is_valid is True
    assert result.validation_result.message == "API is healthy"
    assert result.grading_requests == []
    assert result.evidence is None


@pytest.mark.asyncio
async def test_deployed_api_profile_fails_when_probe_fails(monkeypatch):
    async def fake_validate(base_url):
        return ValidationResult(is_valid=False, message="API unreachable")

    monkeypatch.setattr(engine_module, "validate_deployed_api", fake_validate)

    result = await run_profile(_deployed_api_job())

    assert result.validation_result.is_valid is False
    assert result.grading_requests == []


@pytest.mark.asyncio
async def test_devops_profile_passes_through_deterministic_result(monkeypatch):
    async def fake_workflow(owner, repo, repo_files=None):
        assert owner == "learner"
        assert repo == "devops-repo"
        return ValidationResult(is_valid=True, message="DevOps checks passed")

    monkeypatch.setattr(engine_module, "run_devops_workflow", fake_workflow)

    result = await run_profile(_devops_job())

    assert result.validation_result.is_valid is True
    assert result.validation_result.message == "DevOps checks passed"
    assert result.grading_requests == []
    assert result.evidence is None


@pytest.mark.asyncio
async def test_devops_profile_fails_when_workflow_fails(monkeypatch):
    async def fake_workflow(owner, repo, repo_files=None):
        return ValidationResult(is_valid=False, message="Missing workflow file")

    monkeypatch.setattr(engine_module, "run_devops_workflow", fake_workflow)

    result = await run_profile(_devops_job())

    assert result.validation_result.is_valid is False
    assert result.grading_requests == []


# ---------------------------------------------------------------------------
# Phase 6/7 rubric profiles: security scanning (repo) and career reflection
# (text-only) both gate then record a grading request.
# ---------------------------------------------------------------------------


def _security_job() -> PreparedVerificationJob:
    from learn_to_cloud_shared.testing.requirement_factories import (
        security_scanning_requirement,
    )

    return PreparedVerificationJob(
        id=uuid4(),
        user_id=1,
        github_username="learner",
        requirement=security_scanning_requirement(
            slug="security-scanning",
            required_repo="owner/sec-repo",
        ),
        submitted_value="https://github.com/learner/sec-repo",
    )


def _career_job(text: str) -> PreparedVerificationJob:
    from learn_to_cloud_shared.testing.requirement_factories import (
        career_reflection_requirement,
    )

    return PreparedVerificationJob(
        id=uuid4(),
        user_id=1,
        github_username=None,
        requirement=career_reflection_requirement(slug="career-reflection"),
        submitted_value=text,
    )


@pytest.mark.asyncio
async def test_security_profile_records_grading_request_when_gate_passes(monkeypatch):
    from learn_to_cloud_shared.verification.repo_files import InMemoryRepoFiles
    from learn_to_cloud_shared.verification.tasks.phase6 import (
        SECURITY_SCANNING_RUBRIC_TASK,
    )

    async def fake_gate(owner, repo, repo_files=None):
        return ValidationResult(is_valid=True, message="Dependabot configured")

    monkeypatch.setattr(engine_module, "validate_security_scanning", fake_gate)
    repo_files = InMemoryRepoFiles(
        {".github/dependabot.yml": "version: 2\nupdates: []\n"}
    )

    result = await run_profile(_security_job(), repo_files=repo_files)

    assert result.validation_result.is_valid is True
    assert result.grading_requests is not None
    assert len(result.grading_requests) == 1
    assert result.grading_requests[0].task.id == SECURITY_SCANNING_RUBRIC_TASK.id


@pytest.mark.asyncio
async def test_security_profile_skips_grading_when_gate_fails(monkeypatch):
    from learn_to_cloud_shared.verification.repo_files import InMemoryRepoFiles

    async def fake_gate(owner, repo, repo_files=None):
        return ValidationResult(is_valid=False, message="No scanning found")

    monkeypatch.setattr(engine_module, "validate_security_scanning", fake_gate)

    result = await run_profile(_security_job(), repo_files=InMemoryRepoFiles({}))

    assert result.validation_result.is_valid is False
    assert result.grading_requests == []
    assert result.evidence is None


@pytest.mark.asyncio
async def test_career_profile_records_text_grading_request_when_gate_passes():
    from learn_to_cloud_shared.verification.tasks.phase7 import (
        CAREER_REFLECTION_RUBRIC_TASK,
    )

    text = "A specific, first-person reflection on my target role and projects."
    result = await run_profile(_career_job(text))

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

    result = await run_profile(_career_job(text))

    assert result.validation_result.is_valid is False
    assert result.grading_requests == []
    assert result.evidence is None


# ---------------------------------------------------------------------------
# Phase 0-2 gate-only profiles: profile README, repo fork, CTF and networking
# tokens. All are deterministic (no grading) and require a GitHub username.
# ---------------------------------------------------------------------------


def _phase02_job(requirement, submitted_value, github_username="learner"):
    return PreparedVerificationJob(
        id=uuid4(),
        user_id=1,
        github_username=github_username,
        requirement=requirement,
        submitted_value=submitted_value,
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
    result = await run_profile(job)

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
    result = await run_profile(job)

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
    result = await run_profile(job)

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
    result = await run_profile(job)

    assert result.validation_result.is_valid is False
    assert result.grading_requests == []


@pytest.mark.asyncio
async def test_profile_requiring_username_short_circuits_when_missing():
    from learn_to_cloud_shared.testing.requirement_factories import (
        ctf_token_requirement,
    )

    job = _phase02_job(ctf_token_requirement(), "the-token", github_username=None)
    result = await run_profile(job)

    assert result.validation_result.is_valid is False
    assert result.validation_result.username_match is False
    assert "GitHub username is required" in result.validation_result.message
    assert result.grading_requests == []
