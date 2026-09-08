"""Tests for the versioned unified verification-attempt path.

Covers the deterministic orchestration action sequence (LLM + non-LLM),
exception terminalization, idempotent start (already-exists / ambiguous /
confirmed failure), and reconciler status mapping + age-boundary wiring. The
Durable client and status are faked -- no live Azure calls.
"""

from __future__ import annotations

import json
from collections.abc import Callable, Generator
from contextlib import nullcontext
from datetime import UTC, datetime, timedelta
from typing import Any
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest
from azure.durable_functions import RetryOptions
from learn_to_cloud_shared.models import VerificationAttemptOutcome
from learn_to_cloud_shared.repositories.verification_attempt_repository import (
    AttemptStatusRow,
)
from learn_to_cloud_shared.schemas import ValidationResult
from learn_to_cloud_shared.submission_values import submitted_value_from_raw
from learn_to_cloud_shared.verification.evidence import apply_evidence_cap
from learn_to_cloud_shared.verification.grading_requests import (
    LLMGradingRequest,
    build_text_rubric_message,
)
from learn_to_cloud_shared.verification.tasks.phase7 import (
    CAREER_REFLECTION_RUBRIC_TASK,
)
from learn_to_cloud_shared.verification_attempt_reconciler import stale_cutoff
from learn_to_cloud_shared.verification_workflow import (
    GradingDisposition,
    PreparedVerificationAttempt,
    VerificationRunResult,
)
from learn_to_cloud_shared_test_support.requirement_factories import (
    devops_analysis_requirement,
    journal_api_verifier_requirement,
    repo_fork_requirement,
)

import function_app

# --------------------------------------------------------------------------- #
# Orchestration driver
# --------------------------------------------------------------------------- #


class _RecordedCall:
    def __init__(
        self,
        kind: str,
        name: str,
        payload: object,
        *,
        retry_options: RetryOptions | None = None,
    ) -> None:
        self.kind = kind
        self.name = name
        self.payload = payload
        self.retry_options = retry_options

    def as_tuple(self) -> tuple[str, str]:
        return (self.kind, self.name)


class _FakeOrchestrationContext:
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
        self, name: str, retry_options: RetryOptions, input_: object = None
    ) -> _RecordedCall:
        return _RecordedCall(
            "activity_with_retry", name, input_, retry_options=retry_options
        )


class _Raise:
    def __init__(self, exc: BaseException) -> None:
        self.exc = exc


Responder = Callable[[_RecordedCall], object]


def _reflection_request(text: str = "Complete text 雲") -> LLMGradingRequest:
    task = CAREER_REFLECTION_RUBRIC_TASK
    bundle = apply_evidence_cap(task, [("career-reflection.md", text)])
    return LLMGradingRequest(
        task=task,
        message=build_text_rubric_message(
            requirement_slug="reflection",
            requirement_name="Reflection",
            deterministic_result=ValidationResult(is_valid=True, message="Complete"),
            task=task,
            evidence=bundle.model_dump(mode="json"),
        ),
        thread_id="attempt-reflection",
        allowed_evidence_refs=["career-reflection.md"],
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("corruption", ["truncated", "failed", "incomplete", "invalid"])
async def test_restored_evidence_is_checked_before_provider_call(corruption):
    request = _reflection_request()
    prefix, raw = request.message.split("\n\n", 1)
    message = json.loads(raw)
    if corruption == "truncated":
        message["evidence"]["items"][0]["truncated"] = True
    elif corruption == "failed":
        message["deterministic_result"]["is_valid"] = False
    elif corruption == "incomplete":
        message["deterministic_result"]["verification_completed"] = False
    request_payload = request.model_dump(mode="json")
    request_payload["message"] = f"{prefix}\n\n{json.dumps(message)}"
    if corruption == "invalid":
        request_payload = {}
    provider = AsyncMock()
    with (
        patch("function_app._attached_invocation_context", return_value=nullcontext()),
        patch("function_app.grade_evidence", provider),
    ):
        result = await function_app.run_llm_grading({"request": request_payload}, None)

    assert result == {"outcome": "error", "error_type": "evidence.selection"}
    provider.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize("historical", [False, True])
async def test_complete_restored_request_reaches_provider(historical):
    request = _reflection_request()
    prefix, raw = request.message.split("\n\n", 1)
    message = json.loads(raw)
    if historical:
        message["task"].pop("evidence_contract")
        message["deterministic_result"].pop("error_code")
    request_payload = request.model_dump(mode="json")
    request_payload["message"] = f"{prefix}\n\n{json.dumps(message)}"
    provider = AsyncMock(side_effect=function_app.ContentFilteredError())
    with (
        patch("function_app._attached_invocation_context", return_value=nullcontext()),
        patch("function_app.grade_evidence", provider),
    ):
        result = await function_app.run_llm_grading({"request": request_payload}, None)

    assert result == {"outcome": "content_filtered"}
    provider.assert_awaited_once_with(request_payload["message"])


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("text", "oversized"),
    [
        ("abcd", False),
        ("éé", False),
        ("🦊", False),
        ("abcde", True),
        ("ééé", True),
        ("🦊a", True),
    ],
    ids=[
        "ascii-boundary",
        "two-byte-boundary",
        "four-byte-boundary",
        "ascii-oversized",
        "two-byte-oversized",
        "four-byte-oversized",
    ],
)
async def test_restored_utf8_item_budget_is_checked_before_provider(text, oversized):
    request = _reflection_request(text)
    policy = request.task.evidence.model_copy(update={"max_file_size_bytes": 4})
    task = request.task.model_copy(update={"evidence": policy})
    prefix, raw = request.message.split("\n\n", 1)
    message = json.loads(raw)
    message["task"]["evidence_contract"] = policy.model_dump(mode="json")
    assert message["evidence"]["total_bytes"] == len(text.encode("utf-8"))
    assert message["evidence"]["total_bytes"] < policy.max_total_bytes
    request_payload = request.model_dump(mode="json")
    request_payload["task"] = task.model_dump(mode="json")
    request_payload["message"] = f"{prefix}\n\n{json.dumps(message)}"
    provider = AsyncMock(side_effect=function_app.ContentFilteredError())
    with (
        patch("function_app._attached_invocation_context", return_value=nullcontext()),
        patch("function_app.grade_evidence", provider),
    ):
        result = await function_app.run_llm_grading({"request": request_payload}, None)

    if oversized:
        assert result == {"outcome": "error", "error_type": "evidence.item_limit"}
        provider.assert_not_awaited()
    else:
        assert result == {"outcome": "content_filtered"}
        provider.assert_awaited_once_with(request_payload["message"])


@pytest.mark.asyncio
async def test_restored_evidence_failure_keeps_code_and_drops_transport():
    prepared_payload = _prepared_payload(
        devops_analysis_requirement(slug="devops"),
        "https://github.com/alice/journal",
    )
    run_result = VerificationRunResult(
        attempt=PreparedVerificationAttempt.from_payload(prepared_payload),
        validation_result=ValidationResult(is_valid=True, message="Complete"),
        grading_requests=[_reflection_request()],
    )
    with patch("function_app._attached_invocation_context", return_value=nullcontext()):
        payload = await function_app.llm_grading_failed(
            {
                "run_result": run_result.to_payload(),
                "outcome": "error",
                "error_type": "evidence.selection",
            },
            None,
        )
    restored = VerificationRunResult.from_payload(payload)

    assert restored.validation_result.error_code == "evidence.selection"
    assert restored.validation_result.is_valid is False
    assert restored.validation_result.verification_completed is False
    assert restored.validation_result.task_results is None
    assert restored.llm_error_type is None
    assert restored.evidence is None
    assert restored.grading_requests is None


def _drive(
    gen: Generator[_RecordedCall, object, object],
    responder: Responder,
    *,
    calls: list[_RecordedCall] | None = None,
) -> tuple[list[_RecordedCall], object]:
    calls = calls if calls is not None else []
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
    job = PreparedVerificationAttempt(
        id=uuid4(),
        user_id=1,
        github_username="alice",
        requirement=requirement,
        submitted_value=submitted_value_from_raw(requirement, value),
    )
    return job.to_payload()


def _sequence(calls: list[_RecordedCall]) -> list[tuple[str, str]]:
    return [call.as_tuple() for call in calls]


def _make_responder(
    prepared_payload: dict[str, object],
    *,
    recorded_requests: list[object] | None = None,
    fail_activity: str | None = None,
) -> Responder:
    def responder(call: _RecordedCall) -> object:
        name = call.name
        if fail_activity is not None and name == fail_activity:
            return _Raise(RuntimeError("activity failed"))
        if name == "prepare_verification_attempt":
            return {"attempt": prepared_payload}
        if name == "execute_requirement_verification":
            if recorded_requests is not None:
                return {
                    "validation_result": {"is_valid": True},
                    "grading_requests": recorded_requests,
                }
            return {"status": "verified"}
        if name == "ensure_grading_config":
            return {"valid": True, "missing_vars": []}
        if name == "run_llm_grading":
            return {"outcome": "success", "decision": {"decision": "pass"}}
        if name == "apply_llm_grading_results":
            return {"status": "graded"}
        if name == "finalize_verification_attempt":
            return {"attempt_id": "a-1", "outcome": "succeeded"}
        if name == "terminalize_verification_attempt":
            return {"attempt_id": "a-1", "outcome": "server_error"}
        raise AssertionError(f"unexpected activity call: {name}")

    return responder


class TestAttemptOrchestration:
    @pytest.mark.parametrize(
        "validation",
        [
            {"is_valid": False, "verification_completed": False},
            {"is_valid": False, "verification_completed": True},
            {"is_valid": True, "verification_completed": False},
            {"is_valid": False},
            None,
        ],
    )
    def test_stale_requests_cannot_grade_blocked_evidence(self, validation):
        prepared_payload = _prepared_payload(
            devops_analysis_requirement(slug="devops"),
            "https://github.com/alice/journal",
        )
        run_payload = {
            "validation_result": validation,
            "grading_requests": [{"message": "stale evidence must not be graded"}],
        }
        ctx = _FakeOrchestrationContext({"attempt_id": prepared_payload["id"]})

        def responder(call):
            if call.name == "prepare_verification_attempt":
                return {"attempt": prepared_payload}
            if call.name == "execute_requirement_verification":
                return run_payload
            if call.name == "finalize_verification_attempt":
                assert call.payload is run_payload
                return {"outcome": "server_error"}
            raise AssertionError(f"Unexpected grading activity: {call.name}")

        calls, _ = _drive(function_app._run_attempt_orchestration(ctx), responder)
        assert _sequence(calls) == [
            ("activity_with_retry", "prepare_verification_attempt"),
            ("activity_with_retry", "execute_requirement_verification"),
            ("activity_with_retry", "finalize_verification_attempt"),
        ]

    def test_incomplete_evidence_run_finalizes_without_any_grading_activity(self):
        prepared_payload = _prepared_payload(
            devops_analysis_requirement(slug="devops"),
            "https://github.com/alice/journal",
        )
        prepared = PreparedVerificationAttempt.from_payload(prepared_payload)
        run_payload = VerificationRunResult(
            attempt=prepared,
            validation_result=ValidationResult(
                is_valid=False,
                message="GitHub API error (503). Try again later.",
                verification_completed=False,
            ),
            grading_requests=[],
            grading_disposition=GradingDisposition.SKIPPED_GATE_FAILED,
        ).to_payload()
        ctx = _FakeOrchestrationContext({"attempt_id": str(prepared.id)})
        terminal = {"attempt_id": str(prepared.id), "outcome": "server_error"}

        def responder(call):
            if call.name == "prepare_verification_attempt":
                return {"attempt": prepared_payload}
            if call.name == "execute_requirement_verification":
                return run_payload
            if call.name == "finalize_verification_attempt":
                assert call.payload is run_payload
                restored = VerificationRunResult.from_payload(call.payload)
                assert restored.validation_result.verification_completed is False
                assert restored.grading_requests == []
                return terminal
            raise AssertionError(f"Unexpected grading or error activity: {call.name}")

        calls, result = _drive(function_app._run_attempt_orchestration(ctx), responder)

        assert _sequence(calls) == [
            ("activity_with_retry", "prepare_verification_attempt"),
            ("activity_with_retry", "execute_requirement_verification"),
            ("activity_with_retry", "finalize_verification_attempt"),
        ]
        assert result == terminal

    @pytest.mark.parametrize(
        "requirement",
        [
            repo_fork_requirement(slug="fork", required_repo="owner/repo"),
            journal_api_verifier_requirement(
                slug="journal-api-implementation", required_repo="owner/repo"
            ),
        ],
    )
    def test_non_llm_sequence(self, requirement) -> None:
        payload = _prepared_payload(
            requirement,
            "https://github.com/alice/repo",
        )
        ctx = _FakeOrchestrationContext({"attempt_id": "a-1"})
        responder = _make_responder(payload, recorded_requests=[])
        calls, result = _drive(function_app._run_attempt_orchestration(ctx), responder)
        assert _sequence(calls) == [
            ("activity_with_retry", "prepare_verification_attempt"),
            ("activity_with_retry", "execute_requirement_verification"),
            ("activity_with_retry", "finalize_verification_attempt"),
        ]
        retry_options = calls[1].retry_options
        assert isinstance(retry_options, RetryOptions)
        assert retry_options.max_number_of_attempts == 3
        assert retry_options.first_retry_interval_in_milliseconds == 5000
        assert result == {"attempt_id": "a-1", "outcome": "succeeded"}

    def test_llm_sequence(self) -> None:
        payload = _prepared_payload(
            devops_analysis_requirement(slug="devops"),
            "https://github.com/alice/journal",
        )
        ctx = _FakeOrchestrationContext({"attempt_id": "a-1"})
        responder = _make_responder(payload, recorded_requests=[{"task": "a"}])
        calls, result = _drive(function_app._run_attempt_orchestration(ctx), responder)
        assert _sequence(calls) == [
            ("activity_with_retry", "prepare_verification_attempt"),
            ("activity_with_retry", "execute_requirement_verification"),
            ("activity", "ensure_grading_config"),
            ("activity", "run_llm_grading"),
            ("activity", "apply_llm_grading_results"),
            ("activity_with_retry", "finalize_verification_attempt"),
        ]
        assert calls[3].payload == {"request": {"task": "a"}}
        assert result == {"attempt_id": "a-1", "outcome": "succeeded"}

    @pytest.mark.parametrize("error_type", ["llm.rate_limit", "evidence.selection"])
    def test_llm_error_uses_safe_durable_payload_without_outer_retry(
        self, error_type
    ) -> None:
        payload = _prepared_payload(
            devops_analysis_requirement(slug="devops"),
            "https://github.com/alice/journal",
        )
        prepared = PreparedVerificationAttempt.from_payload(payload)
        outcome = function_app._PreparedOutcome(
            attempt_id="a-1",
            prepared_payload=payload,
            prepared_attempt=prepared,
        )
        ctx = _FakeOrchestrationContext({"attempt_id": "a-1"})

        def responder(call: _RecordedCall) -> object:
            if call.name == "ensure_grading_config":
                return {"valid": True, "missing_vars": []}
            if call.name == "run_llm_grading":
                return {"outcome": "error", "error_type": error_type}
            if call.name == "llm_grading_failed":
                return {"status": "unavailable"}
            raise AssertionError(call.name)

        calls, _ = _drive(
            function_app._llm_grading_step(
                ctx,
                outcome,
                {
                    "validation_result": {"is_valid": True},
                    "grading_requests": [{"task": "a"}],
                },
            ),
            responder,
        )

        assert _sequence(calls) == [
            ("activity", "ensure_grading_config"),
            ("activity", "run_llm_grading"),
            ("activity", "llm_grading_failed"),
        ]
        assert calls[-1].payload == {
            "run_result": {
                "validation_result": {"is_valid": True},
                "grading_requests": [{"task": "a"}],
            },
            "error_type": error_type,
            "outcome": "error",
        }

    def test_content_filter_is_not_retried(self) -> None:
        payload = _prepared_payload(
            devops_analysis_requirement(slug="devops"),
            "https://github.com/alice/journal",
        )
        prepared = PreparedVerificationAttempt.from_payload(payload)
        outcome = function_app._PreparedOutcome(
            attempt_id="a-1",
            prepared_payload=payload,
            prepared_attempt=prepared,
        )
        ctx = _FakeOrchestrationContext({"attempt_id": "a-1"})

        def responder(call: _RecordedCall) -> object:
            if call.name == "ensure_grading_config":
                return {"valid": True, "missing_vars": []}
            if call.name == "run_llm_grading":
                return {"outcome": "content_filtered"}
            if call.name == "llm_grading_failed":
                return {"status": "filtered"}
            raise AssertionError(call.name)

        calls, _ = _drive(
            function_app._llm_grading_step(
                ctx,
                outcome,
                {
                    "validation_result": {"is_valid": True},
                    "grading_requests": [{"task": "a"}],
                },
            ),
            responder,
        )
        assert _sequence(calls) == [
            ("activity", "ensure_grading_config"),
            ("activity", "run_llm_grading"),
            ("activity", "llm_grading_failed"),
        ]
        assert calls[-1].payload["outcome"] == "content_filtered"

    def test_unknown_durable_error_category_is_normalized(self) -> None:
        payload = _prepared_payload(
            devops_analysis_requirement(slug="devops"),
            "https://github.com/alice/journal",
        )
        prepared = PreparedVerificationAttempt.from_payload(payload)
        outcome = function_app._PreparedOutcome(
            attempt_id="a-1",
            prepared_payload=payload,
            prepared_attempt=prepared,
        )
        ctx = _FakeOrchestrationContext({"attempt_id": "a-1"})

        def responder(call: _RecordedCall) -> object:
            if call.name == "ensure_grading_config":
                return {"valid": True, "missing_vars": []}
            if call.name == "run_llm_grading":
                return {"outcome": "error", "error_type": "provider raw detail"}
            if call.name == "llm_grading_failed":
                return {"status": "unavailable"}
            raise AssertionError(call.name)

        calls, _ = _drive(
            function_app._llm_grading_step(
                ctx,
                outcome,
                {
                    "validation_result": {"is_valid": True},
                    "grading_requests": [{"task": "a"}],
                },
            ),
            responder,
        )
        assert calls[-1].payload["error_type"] == "llm.unknown"

    @pytest.mark.parametrize(
        ("fail_activity", "expected_activities", "terminal_source"),
        [
            (
                "prepare_verification_attempt",
                ["prepare_verification_attempt", "terminalize_verification_attempt"],
                "orchestrator_prepare_exception",
            ),
            (
                "execute_requirement_verification",
                [
                    "prepare_verification_attempt",
                    "execute_requirement_verification",
                    "terminalize_verification_attempt",
                ],
                "orchestrator_verification_exception",
            ),
        ],
        ids=["prepare", "verify"],
    )
    def test_activity_failure_terminalizes(
        self, fail_activity, expected_activities, terminal_source
    ) -> None:
        payload = _prepared_payload(
            repo_fork_requirement(slug="fork", required_repo="owner/repo"),
            "https://github.com/alice/repo",
        )
        ctx = _FakeOrchestrationContext({"attempt_id": "a-1"})
        responder = _make_responder(payload, fail_activity=fail_activity)
        calls: list[_RecordedCall] = []
        with pytest.raises(RuntimeError, match="activity failed"):
            _drive(
                function_app._run_attempt_orchestration(ctx),
                responder,
                calls=calls,
            )
        assert _sequence(calls) == [
            ("activity_with_retry", name) for name in expected_activities
        ]
        assert calls[-1].payload["terminal_source"] == terminal_source


class TestVersionedOrchestratorRegistered:
    def test_versioned_name_and_symbol(self) -> None:
        assert (
            function_app._ATTEMPT_ORCHESTRATOR_NAME
            == "verification_attempt_orchestrator_v1"
        )
        assert hasattr(function_app, function_app._ATTEMPT_ORCHESTRATOR_NAME)


# --------------------------------------------------------------------------- #
# Fake Durable client / status
# --------------------------------------------------------------------------- #


class _FakeStatus:
    def __init__(self, runtime_status: object) -> None:
        self.runtime_status = runtime_status


class _FakeRuntimeStatus:
    def __init__(self, name: str) -> None:
        self.name = name


class _FakeClient:
    def __init__(
        self,
        *,
        statuses: dict[str, object] | None = None,
        start_raises: bool = False,
    ) -> None:
        self._statuses = statuses or {}
        self._start_raises = start_raises
        self.started: list[str] = []

    async def get_status(self, instance_id, **_kwargs):
        return self._statuses.get(instance_id)

    async def start_new(self, name, *, instance_id, client_input):
        if self._start_raises:
            raise RuntimeError("ambiguous start")
        self.started.append(instance_id)
        return instance_id


class _FakeSession:
    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False


def _session_maker():
    return _FakeSession()


class TestStartIdempotency:
    pytestmark = pytest.mark.asyncio

    async def _start(
        self,
        client,
        attempt_id,
        *,
        claim=function_app._StartClaim.CLAIMED,
    ):
        with patch.object(
            function_app,
            "_claim_attempt_start",
            new=AsyncMock(return_value=claim),
        ):
            return await function_app._start_attempt_orchestration(
                client, attempt_id, session_maker=_session_maker
            )

    async def test_already_existing_instance_is_success(self) -> None:
        attempt_id = uuid4()
        client = _FakeClient(
            statuses={str(attempt_id): _FakeStatus(_FakeRuntimeStatus("Running"))}
        )
        outcome = await self._start(
            client,
            attempt_id,
            claim=function_app._StartClaim.ALREADY_CLAIMED,
        )
        assert outcome is function_app._StartOutcome.ALREADY_EXISTS
        assert client.started == []

    async def test_fresh_start(self) -> None:
        attempt_id = uuid4()
        client = _FakeClient()
        outcome = await self._start(client, attempt_id)
        assert outcome is function_app._StartOutcome.STARTED
        assert client.started == [str(attempt_id)]

    async def test_ambiguous_but_started(self) -> None:
        attempt_id = uuid4()
        # start_new raises, but a follow-up status shows the instance exists,
        # so the start is treated as success rather than a failure.
        outcome = await self._start(_AmbiguousClient(attempt_id), attempt_id)
        assert outcome is function_app._StartOutcome.AMBIGUOUS_STARTED

    async def test_existing_claim_without_visible_instance_does_not_restart(
        self,
    ) -> None:
        attempt_id = uuid4()
        client = _FakeClient()
        with patch.object(function_app.asyncio, "sleep", new=AsyncMock()):
            outcome = await self._start(
                client,
                attempt_id,
                claim=function_app._StartClaim.ALREADY_CLAIMED,
            )
        assert outcome is function_app._StartOutcome.ALREADY_CLAIMED
        assert client.started == []

    async def test_terminal_attempt_does_not_restart(self) -> None:
        attempt_id = uuid4()
        client = _FakeClient()
        outcome = await self._start(
            client,
            attempt_id,
            claim=function_app._StartClaim.TERMINAL,
        )
        assert outcome is function_app._StartOutcome.ALREADY_EXISTS
        assert client.started == []

    async def test_ambiguous_start_waits_for_delayed_status(self) -> None:
        attempt_id = uuid4()
        client = _DelayedStatusClient(attempt_id)
        with patch.object(function_app.asyncio, "sleep", new=AsyncMock()):
            outcome = await self._start(client, attempt_id)
        assert outcome is function_app._StartOutcome.AMBIGUOUS_STARTED

    async def test_confirmed_start_failure_terminalizes(self) -> None:
        attempt_id = uuid4()
        client = _FakeClient(start_raises=True)
        with (
            patch.object(function_app.asyncio, "sleep", new=AsyncMock()),
            patch.object(function_app, "terminalize_attempt", new=AsyncMock()) as term,
        ):
            outcome = await self._start(client, attempt_id)
        assert outcome is function_app._StartOutcome.START_FAILED
        term.assert_awaited_once()
        assert term.await_args.kwargs["terminal_source"] == "start_failure"

    async def test_unconfirmed_start_failure_does_not_terminalize(self) -> None:
        attempt_id = uuid4()
        client = _UnqueryableAfterStartClient()
        with (
            patch.object(function_app.asyncio, "sleep", new=AsyncMock()),
            patch.object(function_app, "terminalize_attempt", new=AsyncMock()) as term,
            pytest.raises(RuntimeError, match="could not confirm"),
        ):
            await self._start(client, attempt_id)
        term.assert_not_awaited()


class _AmbiguousClient:
    """A client whose instance does not exist until after start_new raises."""

    def __init__(self, attempt_id) -> None:
        self._id = str(attempt_id)
        self._exists = False
        self.started: list[str] = []

    async def get_status(self, instance_id, **_kwargs):
        if instance_id == self._id and self._exists:
            return _FakeStatus(_FakeRuntimeStatus("Pending"))
        return None

    async def start_new(self, name, *, instance_id, client_input):
        # The instance actually started, but the call surfaced an error.
        self._exists = True
        raise RuntimeError("ambiguous start")


class _DelayedStatusClient:
    def __init__(self, attempt_id) -> None:
        self._id = str(attempt_id)
        self._query_count = 0

    async def get_status(self, instance_id, **_kwargs):
        assert instance_id == self._id
        self._query_count += 1
        if self._query_count >= 2:
            return _FakeStatus(_FakeRuntimeStatus("Pending"))
        return None

    async def start_new(self, name, *, instance_id, client_input):
        raise RuntimeError("ambiguous start")


class _UnqueryableAfterStartClient:
    def __init__(self) -> None:
        self._query_count = 0

    async def get_status(self, instance_id, **_kwargs):
        self._query_count += 1
        raise RuntimeError("status unavailable")

    async def start_new(self, name, *, instance_id, client_input):
        raise RuntimeError("ambiguous start")


# --------------------------------------------------------------------------- #
# Reconciler
# --------------------------------------------------------------------------- #


def _status_row(attempt_id, created_at) -> AttemptStatusRow:
    return AttemptStatusRow(
        id=attempt_id,
        user_id=1,
        requirement_uuid=uuid4(),
        outcome=None,
        started_at=None,
        created_at=created_at,
    )


class _CapturingRepo:
    captured_cutoff: object = None

    def __init__(self, db) -> None:
        pass

    async def list_active_older_than(self, cutoff, *, limit):
        _CapturingRepo.captured_cutoff = cutoff
        return _CapturingRepo.rows

    async def get_status(self, attempt_id):
        return next(
            (row for row in _CapturingRepo.rows if row.id == attempt_id),
            None,
        )


class _TerminalOnRecheckRepo(_CapturingRepo):
    async def get_status(self, attempt_id):
        row = await super().get_status(attempt_id)
        if row is None:
            return None
        return AttemptStatusRow(
            id=row.id,
            user_id=row.user_id,
            requirement_uuid=row.requirement_uuid,
            outcome="succeeded",
            started_at=row.started_at,
            created_at=row.created_at,
        )


class TestReconciler:
    pytestmark = pytest.mark.asyncio

    async def test_maps_statuses_and_reports_stuck_healthy_attempt(
        self,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        failed = uuid4()
        terminated = uuid4()
        completed = uuid4()
        missing = uuid4()
        running = uuid4()
        now = datetime(2026, 1, 1, 12, 0, tzinfo=UTC)
        old = now - timedelta(hours=2)
        rows = [
            _status_row(failed, old),
            _status_row(terminated, old),
            _status_row(completed, old),
            _status_row(missing, old),
            _status_row(running, old),
        ]
        _CapturingRepo.rows = rows
        client = _FakeClient(
            statuses={
                str(failed): _FakeStatus(_FakeRuntimeStatus("Failed")),
                str(terminated): _FakeStatus(_FakeRuntimeStatus("Canceled")),
                str(completed): _FakeStatus(_FakeRuntimeStatus("Completed")),
                # ``missing`` has no status entry -> confirmed not started.
                str(running): _FakeStatus(_FakeRuntimeStatus("Running")),
            }
        )
        with (
            patch.object(function_app, "VerificationAttemptRepository", _CapturingRepo),
            patch.object(function_app, "terminalize_attempt", new=AsyncMock()) as term,
            caplog.at_level(
                "WARNING",
                logger="function_app",
            ),
        ):
            summary = await function_app._reconcile_stale_attempts(
                client,
                session_maker=_session_maker,
                stale_attempt_min_age_minutes=30,
                batch_limit=50,
                now=now,
            )

        assert summary.candidate_count == 5
        assert summary.terminalized_count == 4
        assert summary.stuck_count == 1
        assert _CapturingRepo.captured_cutoff == stale_cutoff(now, 30)

        terminalized = {
            call.args[0]: call.kwargs["outcome"] for call in term.await_args_list
        }
        assert terminalized[failed] is VerificationAttemptOutcome.SERVER_ERROR
        assert terminalized[terminated] is VerificationAttemptOutcome.CANCELLED
        assert terminalized[completed] is VerificationAttemptOutcome.SERVER_ERROR
        assert terminalized[missing] is VerificationAttemptOutcome.SERVER_ERROR
        assert running not in terminalized
        stuck_record = next(
            record
            for record in caplog.records
            if record.message == "verification.attempt.stuck"
        )
        assert stuck_record.__dict__["verification.attempt.id"] == str(running)
        assert stuck_record.__dict__["verification.durable.status"] == "Running"
        assert (
            stuck_record.__dict__["verification.stuck.reason"] == "active_beyond_limit"
        )

    async def test_rechecks_missing_status_before_terminalizing(self) -> None:
        attempt_id = uuid4()
        now = datetime(2026, 1, 1, 12, 0, tzinfo=UTC)
        _CapturingRepo.rows = [_status_row(attempt_id, now - timedelta(hours=2))]
        client = _MissingThenRunningClient(attempt_id)
        with (
            patch.object(function_app, "VerificationAttemptRepository", _CapturingRepo),
            patch.object(function_app, "terminalize_attempt", new=AsyncMock()) as term,
        ):
            summary = await function_app._reconcile_stale_attempts(
                client,
                session_maker=_session_maker,
                stale_attempt_min_age_minutes=30,
                batch_limit=50,
                now=now,
            )
        assert summary.terminalized_count == 0
        assert summary.stuck_count == 1
        term.assert_not_awaited()

    async def test_does_not_report_stuck_after_database_finalization(
        self,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        attempt_id = uuid4()
        now = datetime(2026, 1, 1, 12, 0, tzinfo=UTC)
        _CapturingRepo.rows = [_status_row(attempt_id, now - timedelta(hours=2))]
        client = _FakeClient(
            statuses={
                str(attempt_id): _FakeStatus(_FakeRuntimeStatus("Running")),
            }
        )

        with (
            patch.object(
                function_app,
                "VerificationAttemptRepository",
                _TerminalOnRecheckRepo,
            ),
            caplog.at_level("WARNING", logger="function_app"),
        ):
            summary = await function_app._reconcile_stale_attempts(
                client,
                session_maker=_session_maker,
                stale_attempt_min_age_minutes=30,
                batch_limit=50,
                now=now,
            )

        assert summary.stuck_count == 0
        assert not any(
            record.message == "verification.attempt.stuck" for record in caplog.records
        )


class _MissingThenRunningClient:
    def __init__(self, attempt_id) -> None:
        self._id = str(attempt_id)
        self._query_count = 0

    async def get_status(self, instance_id, **_kwargs):
        assert instance_id == self._id
        self._query_count += 1
        if self._query_count == 1:
            return None
        return _FakeStatus(_FakeRuntimeStatus("Running"))
