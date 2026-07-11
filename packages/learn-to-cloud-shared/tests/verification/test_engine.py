"""Tests for the declarative verification engine."""

from uuid import uuid4

import pytest

from learn_to_cloud_shared.schemas import TaskResult, ValidationResult
from learn_to_cloud_shared.testing.requirement_factories import (
    career_reflection_requirement,
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

    result = await run_profile(_job(career_reflection_requirement()))

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
