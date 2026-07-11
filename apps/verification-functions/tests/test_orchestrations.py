"""Verification orchestration workflow tests.

The Durable orchestration generator is driven manually here: a fake
context records each yielded activity call, and the test feeds back the
activity result. This asserts the exact sequence of activity calls the
single workflow makes. LLM grading is data-driven -- the workflow calls
``collect_llm_grading_requests`` for every submission type and only grades
when that activity returns requests, so deterministic phases pass straight
through with an empty request list.
"""

from __future__ import annotations

from collections.abc import Callable, Generator
from typing import Any
from uuid import uuid4

import function_app
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
    recorded_requests: list[object] | None = None,
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
            if recorded_requests is not None:
                return {"status": "verified", "grading_requests": recorded_requests}
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


class TestCanonicalWorkflow:
    """The single verification workflow used by every submission type."""

    def test_grades_when_requests_present(self) -> None:
        payload = _graded_payload()
        ctx = _FakeOrchestrationContext({"id": "job-1", **payload})
        responder = _make_responder(
            payload, llm_requests=[{"task": "a"}, {"task": "b"}]
        )
        calls, result = _drive(
            function_app._run_verification_orchestration(ctx), responder
        )
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

    def test_uses_recorded_grading_requests_and_skips_probe(self) -> None:
        # A migrated profile records grading requests on the verify result;
        # the orchestrator grades those directly and skips the legacy probe.
        payload = _graded_payload()
        ctx = _FakeOrchestrationContext({"id": "job-1", **payload})
        responder = _make_responder(payload, recorded_requests=[{"task": "a"}])
        calls, result = _drive(
            function_app._run_verification_orchestration(ctx), responder
        )
        assert _sequence(calls) == [
            ("activity_with_retry", "prepare_verification_job"),
            ("activity_with_retry", "execute_requirement_verification"),
            ("activity", "ensure_grading_config"),
            ("activity_with_retry", "run_llm_grading"),
            ("activity", "apply_llm_grading_results"),
            ("activity_with_retry", "persist_verification_result"),
        ]
        assert result == {
            "job_id": "job-1",
            "status": "completed",
            "submission_id": 7,
        }

    def test_recorded_empty_requests_skip_grading_and_probe(self) -> None:
        # A migrated profile whose gate failed records an empty list; the
        # orchestrator skips grading entirely (no probe, no LLM calls).
        payload = _graded_payload()
        ctx = _FakeOrchestrationContext({"id": "job-1", **payload})
        responder = _make_responder(payload, recorded_requests=[])
        calls, _ = _drive(function_app._run_verification_orchestration(ctx), responder)
        assert _sequence(calls) == [
            ("activity_with_retry", "prepare_verification_job"),
            ("activity_with_retry", "execute_requirement_verification"),
            ("activity_with_retry", "persist_verification_result"),
        ]

    def test_skips_grading_when_no_requests(self) -> None:
        payload = _graded_payload()
        ctx = _FakeOrchestrationContext({"id": "job-1", **payload})
        responder = _make_responder(payload, llm_requests=[])
        calls, _ = _drive(function_app._run_verification_orchestration(ctx), responder)
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
        calls, _ = _drive(function_app._run_verification_orchestration(ctx), responder)
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
        calls, _ = _drive(function_app._run_verification_orchestration(ctx), responder)
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
        calls, result = _drive(
            function_app._run_verification_orchestration(ctx), responder
        )
        assert _sequence(calls) == [
            ("activity_with_retry", "prepare_verification_job"),
        ]
        assert result == terminal


class TestDeterministicSubmissionTypes:
    """Deterministic types (e.g. phase 4 deployed_api) run the same single
    workflow: they call ``collect_llm_grading_requests``, get an empty list,
    and skip grading -- no separate deterministic orchestrator."""

    def test_passes_through_grading_with_no_requests(self) -> None:
        payload = _deterministic_payload()
        ctx = _FakeOrchestrationContext({"id": "job-1", **payload})
        responder = _make_responder(payload, llm_requests=[])
        calls, result = _drive(
            function_app._run_verification_orchestration(ctx), responder
        )
        assert _sequence(calls) == [
            ("activity_with_retry", "prepare_verification_job"),
            ("activity_with_retry", "execute_requirement_verification"),
            ("activity", "collect_llm_grading_requests"),
            ("activity_with_retry", "persist_verification_result"),
        ]
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
        calls, result = _drive(
            function_app._run_verification_orchestration(ctx), responder
        )
        assert _sequence(calls) == [
            ("activity_with_retry", "prepare_verification_job"),
        ]
        assert result == terminal


class TestSingleOrchestrator:
    def test_all_submission_types_use_one_orchestrator(self) -> None:
        assert function_app._ORCHESTRATOR_NAME == "verification_orchestrator"
        assert hasattr(function_app, function_app._ORCHESTRATOR_NAME)


class TestContentFilterClassification:
    def test_matches_typed_error_name(self) -> None:
        assert function_app._is_content_filter_failure("ContentFilteredError", "x")

    def test_matches_marker_in_detail(self) -> None:
        detail = "Activity failed: content_filter: blocked by Azure"
        assert function_app._is_content_filter_failure("Exception", detail)

    def test_ignores_unrelated_failures(self) -> None:
        assert not function_app._is_content_filter_failure("RuntimeError", "timeout")
