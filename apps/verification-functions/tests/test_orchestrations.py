"""Per-phase orchestration workflow tests (issue #429).

The Durable orchestration generators are driven manually here: a fake
context records each yielded activity call, and the test feeds back the
activity result. This asserts the exact sequence of activity calls each
workflow makes, including the determinism-critical difference that the
deterministic workflow (phases 4 and 5) never calls
``collect_llm_grading_requests`` while the graded workflow (phases 3 and
6) does.
"""

from __future__ import annotations

from collections.abc import Callable, Generator
from typing import Any
from uuid import uuid4

import function_app
from learn_to_cloud_shared.models import SubmissionType
from learn_to_cloud_shared.testing.requirement_factories import (
    deployed_api_requirement,
    journal_api_verifier_requirement,
)
from learn_to_cloud_shared.verification_job_executor import PreparedVerificationJob


class _RecordedCall:
    """A single activity call yielded by an orchestration generator."""

    def __init__(self, kind: str, name: str, payload: object) -> None:
        self.kind = kind
        self.name = name
        self.payload = payload

    def as_tuple(self) -> tuple[str, str]:
        return (self.kind, self.name)


class _FakeOrchestrationContext:
    """Minimal stand-in for ``DurableOrchestrationContext``.

    Records custom-status updates and returns a :class:`_RecordedCall`
    for each activity invocation so the driver can assert the call
    sequence and feed back results.
    """

    def __init__(self, job_input: object) -> None:
        self._input = job_input
        self.statuses: list[object] = []

    def get_input(self) -> object:
        return self._input

    def set_custom_status(self, status: object) -> None:
        self.statuses.append(status)

    def call_activity(self, name: str, input_: object = None) -> _RecordedCall:
        return _RecordedCall("activity", name, input_)

    def call_activity_with_retry(
        self, name: str, retry_options: object, input_: object = None
    ) -> _RecordedCall:
        return _RecordedCall("activity_with_retry", name, input_)


class _Raise:
    """Marker telling the driver to throw into the generator (activity failure)."""

    def __init__(self, exc: BaseException) -> None:
        self.exc = exc


Responder = Callable[[_RecordedCall], object]


def _drive(
    gen: Generator[_RecordedCall, object, object], responder: Responder
) -> tuple[list[_RecordedCall], object]:
    """Run an orchestration generator, feeding each yielded call a result."""
    calls: list[_RecordedCall] = []
    try:
        call = next(gen)
    except StopIteration as stop:
        return calls, stop.value
    while True:
        calls.append(call)
        result = responder(call)
        try:
            if isinstance(result, _Raise):
                call = gen.throw(result.exc)
            else:
                call = gen.send(result)
        except StopIteration as stop:
            return calls, stop.value


def _prepared_payload(requirement: Any, value: str) -> dict[str, object]:
    job = PreparedVerificationJob(
        id=uuid4(),
        user_id=1,
        github_username="alice",
        requirement=requirement,
        submitted_value=value,
    )
    return job.to_payload()


def _graded_payload() -> dict[str, object]:
    return _prepared_payload(
        journal_api_verifier_requirement(slug="journal-api-implementation"),
        "https://github.com/alice/journal",
    )


def _deterministic_payload() -> dict[str, object]:
    return _prepared_payload(
        deployed_api_requirement(slug="deployed-api"),
        "https://api.example.com",
    )


def _make_responder(
    prepared_payload: dict[str, object],
    *,
    llm_requests: list[object] | None = None,
    config_valid: bool = True,
    fail_activity: str | None = None,
    terminal: object | None = None,
) -> Responder:
    def responder(call: _RecordedCall) -> object:
        name = call.name
        if fail_activity is not None and name == fail_activity:
            return _Raise(RuntimeError("activity failed"))
        if name == "prepare_verification_job":
            if terminal is not None:
                return {"terminal_result": terminal}
            return {"job": prepared_payload}
        if name == "execute_requirement_verification":
            return {"status": "verified"}
        if name == "collect_llm_grading_requests":
            return list(llm_requests or [])
        if name == "ensure_grading_config":
            return {
                "valid": config_valid,
                "missing_vars": [] if config_valid else ["AZURE_AI_FOUNDRY_ENDPOINT"],
            }
        if name == "run_llm_grading":
            return {"decision": "pass"}
        if name == "apply_llm_grading_results":
            return {"status": "graded"}
        if name == "llm_grading_failed":
            return {"status": "failed"}
        if name == "persist_verification_result":
            return {"job_id": "job-1", "status": "completed", "submission_id": 7}
        raise AssertionError(f"unexpected activity call: {name}")

    return responder


def _sequence(calls: list[_RecordedCall]) -> list[tuple[str, str]]:
    return [call.as_tuple() for call in calls]


class TestGradedWorkflow:
    def test_grades_when_requests_present(self) -> None:
        payload = _graded_payload()
        ctx = _FakeOrchestrationContext({"id": "job-1", **payload})
        responder = _make_responder(
            payload, llm_requests=[{"task": "a"}, {"task": "b"}]
        )
        calls, result = _drive(function_app._graded_verification(ctx), responder)
        assert _sequence(calls) == [
            ("activity_with_retry", "prepare_verification_job"),
            ("activity_with_retry", "execute_requirement_verification"),
            ("activity", "collect_llm_grading_requests"),
            ("activity", "ensure_grading_config"),
            ("activity_with_retry", "run_llm_grading"),
            ("activity_with_retry", "run_llm_grading"),
            ("activity", "apply_llm_grading_results"),
            ("activity_with_retry", "persist_verification_result"),
        ]
        assert result == {
            "job_id": "job-1",
            "status": "completed",
            "submission_id": 7,
        }

    def test_skips_grading_when_no_requests(self) -> None:
        payload = _graded_payload()
        ctx = _FakeOrchestrationContext({"id": "job-1", **payload})
        responder = _make_responder(payload, llm_requests=[])
        calls, _ = _drive(function_app._graded_verification(ctx), responder)
        assert _sequence(calls) == [
            ("activity_with_retry", "prepare_verification_job"),
            ("activity_with_retry", "execute_requirement_verification"),
            ("activity", "collect_llm_grading_requests"),
            ("activity_with_retry", "persist_verification_result"),
        ]

    def test_missing_grading_config_fails_gracefully(self) -> None:
        payload = _graded_payload()
        ctx = _FakeOrchestrationContext({"id": "job-1", **payload})
        responder = _make_responder(
            payload, llm_requests=[{"task": "a"}], config_valid=False
        )
        calls, _ = _drive(function_app._graded_verification(ctx), responder)
        assert _sequence(calls) == [
            ("activity_with_retry", "prepare_verification_job"),
            ("activity_with_retry", "execute_requirement_verification"),
            ("activity", "collect_llm_grading_requests"),
            ("activity", "ensure_grading_config"),
            ("activity", "llm_grading_failed"),
            ("activity_with_retry", "persist_verification_result"),
        ]

    def test_grading_activity_failure_falls_back(self) -> None:
        payload = _graded_payload()
        ctx = _FakeOrchestrationContext({"id": "job-1", **payload})
        responder = _make_responder(
            payload,
            llm_requests=[{"task": "a"}],
            fail_activity="run_llm_grading",
        )
        calls, _ = _drive(function_app._graded_verification(ctx), responder)
        assert _sequence(calls) == [
            ("activity_with_retry", "prepare_verification_job"),
            ("activity_with_retry", "execute_requirement_verification"),
            ("activity", "collect_llm_grading_requests"),
            ("activity", "ensure_grading_config"),
            ("activity_with_retry", "run_llm_grading"),
            ("activity", "llm_grading_failed"),
            ("activity_with_retry", "persist_verification_result"),
        ]

    def test_terminal_preparation_returns_without_verifying(self) -> None:
        payload = _graded_payload()
        ctx = _FakeOrchestrationContext({"id": "job-1", **payload})
        terminal = {"job_id": "job-1", "status": "completed", "submission_id": 1}
        responder = _make_responder(payload, terminal=terminal)
        calls, result = _drive(function_app._graded_verification(ctx), responder)
        assert _sequence(calls) == [
            ("activity_with_retry", "prepare_verification_job"),
        ]
        assert result == terminal


class TestDeterministicWorkflow:
    def test_never_calls_collect_llm_grading(self) -> None:
        payload = _deterministic_payload()
        ctx = _FakeOrchestrationContext({"id": "job-1", **payload})
        responder = _make_responder(payload)
        calls, result = _drive(function_app._deterministic_verification(ctx), responder)
        assert _sequence(calls) == [
            ("activity_with_retry", "prepare_verification_job"),
            ("activity_with_retry", "execute_requirement_verification"),
            ("activity_with_retry", "persist_verification_result"),
        ]
        assert all(call.name != "collect_llm_grading_requests" for call in calls)
        assert result == {
            "job_id": "job-1",
            "status": "completed",
            "submission_id": 7,
        }

    def test_terminal_preparation_returns_without_verifying(self) -> None:
        payload = _deterministic_payload()
        ctx = _FakeOrchestrationContext({"id": "job-1", **payload})
        terminal = {"job_id": "job-1", "status": "completed", "submission_id": 1}
        responder = _make_responder(payload, terminal=terminal)
        calls, result = _drive(function_app._deterministic_verification(ctx), responder)
        assert _sequence(calls) == [
            ("activity_with_retry", "prepare_verification_job"),
        ]
        assert result == terminal


class TestLegacyDrainBody:
    def test_deployed_api_still_calls_collect_on_legacy_body(self) -> None:
        """In-flight phase 4/5 jobs replay on the legacy body, which keeps
        the collect call so their recorded history still matches."""
        payload = _deterministic_payload()
        ctx = _FakeOrchestrationContext({"id": "job-1", **payload})
        responder = _make_responder(payload, llm_requests=[])
        calls, _ = _drive(function_app._run_verification_orchestration(ctx), responder)
        assert _sequence(calls) == [
            ("activity_with_retry", "prepare_verification_job"),
            ("activity_with_retry", "execute_requirement_verification"),
            ("activity", "collect_llm_grading_requests"),
            ("activity_with_retry", "persist_verification_result"),
        ]


class TestOrchestratorNameMapping:
    def test_phase4_and_phase5_use_v2_names(self) -> None:
        names = function_app._ORCHESTRATOR_NAMES_BY_SUBMISSION_TYPE
        assert (
            names[SubmissionType.DEPLOYED_API]
            == "verify_phase4_deployed_api_orchestrator_v2"
        )
        assert (
            names[SubmissionType.DEVOPS_ANALYSIS]
            == "verify_phase5_devops_orchestrator_v2"
        )

    def test_phase3_and_phase6_keep_legacy_names(self) -> None:
        names = function_app._ORCHESTRATOR_NAMES_BY_SUBMISSION_TYPE
        assert (
            names[SubmissionType.JOURNAL_API_VERIFIER]
            == "verify_phase3_journal_api_verifier_orchestrator"
        )
        assert (
            names[SubmissionType.SECURITY_SCANNING]
            == "verify_phase6_security_orchestrator"
        )

    def test_every_mapped_name_is_registered(self) -> None:
        """Guards against pointing the resolver at a non-existent orchestrator."""
        for name in function_app._ORCHESTRATOR_NAMES_BY_SUBMISSION_TYPE.values():
            assert hasattr(function_app, name), f"missing orchestrator: {name}"

    def test_legacy_drain_names_remain_registered(self) -> None:
        for name in (
            "verify_phase4_deployed_api_orchestrator",
            "verify_phase5_devops_orchestrator",
        ):
            assert hasattr(function_app, name), f"missing drain orchestrator: {name}"
