"""Tests for the versioned unified verification-attempt path.

Covers the deterministic orchestration action sequence (LLM + non-LLM),
exception terminalization, idempotent start (already-exists / ambiguous /
confirmed failure), and reconciler status mapping + age-boundary wiring. The
Durable client and status are faked -- no live Azure calls.
"""

from __future__ import annotations

from collections.abc import Callable, Generator
from datetime import UTC, datetime, timedelta
from typing import Any
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import function_app
import pytest
from learn_to_cloud_shared.models import VerificationAttemptOutcome
from learn_to_cloud_shared.repositories.verification_attempt_repository import (
    AttemptStatusRow,
)
from learn_to_cloud_shared.submission_values import SubmittedValue
from learn_to_cloud_shared.testing.requirement_factories import (
    journal_api_verifier_requirement,
    repo_fork_requirement,
)
from learn_to_cloud_shared.verification_attempt_reconciler import stale_cutoff
from learn_to_cloud_shared.verification_workflow import PreparedVerificationAttempt


# --------------------------------------------------------------------------- #
# Orchestration driver
# --------------------------------------------------------------------------- #


class _RecordedCall:
    def __init__(self, kind: str, name: str, payload: object) -> None:
        self.kind = kind
        self.name = name
        self.payload = payload

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
        self, name: str, retry_options: object, input_: object = None
    ) -> _RecordedCall:
        return _RecordedCall("activity_with_retry", name, input_)


class _Raise:
    def __init__(self, exc: BaseException) -> None:
        self.exc = exc


Responder = Callable[[_RecordedCall], object]


def _drive(
    gen: Generator[_RecordedCall, object, object], responder: Responder
) -> tuple[list[_RecordedCall], object]:
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
    job = PreparedVerificationAttempt(
        id=uuid4(),
        user_id=1,
        github_username="alice",
        requirement=requirement,
        submitted_value=SubmittedValue.from_raw(requirement, value),
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
                return {"status": "verified", "grading_requests": recorded_requests}
            return {"status": "verified"}
        if name == "ensure_grading_config":
            return {"valid": True, "missing_vars": []}
        if name == "run_llm_grading":
            return {"decision": "pass"}
        if name == "apply_llm_grading_results":
            return {"status": "graded"}
        if name == "finalize_verification_attempt":
            return {"attempt_id": "a-1", "outcome": "succeeded"}
        if name == "terminalize_verification_attempt":
            return {"attempt_id": "a-1", "outcome": "server_error"}
        raise AssertionError(f"unexpected activity call: {name}")

    return responder


class TestAttemptOrchestration:
    def test_non_llm_sequence(self) -> None:
        payload = _prepared_payload(
            repo_fork_requirement(slug="fork", required_repo="owner/repo"),
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
        assert result == {"attempt_id": "a-1", "outcome": "succeeded"}

    def test_llm_sequence(self) -> None:
        payload = _prepared_payload(
            journal_api_verifier_requirement(slug="journal"),
            "https://github.com/alice/journal",
        )
        ctx = _FakeOrchestrationContext({"attempt_id": "a-1"})
        responder = _make_responder(payload, recorded_requests=[{"task": "a"}])
        calls, result = _drive(function_app._run_attempt_orchestration(ctx), responder)
        assert _sequence(calls) == [
            ("activity_with_retry", "prepare_verification_attempt"),
            ("activity_with_retry", "execute_requirement_verification"),
            ("activity", "ensure_grading_config"),
            ("activity_with_retry", "run_llm_grading"),
            ("activity", "apply_llm_grading_results"),
            ("activity_with_retry", "finalize_verification_attempt"),
        ]
        assert result == {"attempt_id": "a-1", "outcome": "succeeded"}

    def test_prepare_failure_terminalizes(self) -> None:
        payload = _prepared_payload(
            repo_fork_requirement(slug="fork", required_repo="owner/repo"),
            "https://github.com/alice/repo",
        )
        ctx = _FakeOrchestrationContext({"attempt_id": "a-1"})
        responder = _make_responder(
            payload, fail_activity="prepare_verification_attempt"
        )
        calls, result = _drive(function_app._run_attempt_orchestration(ctx), responder)
        assert _sequence(calls) == [
            ("activity_with_retry", "prepare_verification_attempt"),
            ("activity_with_retry", "terminalize_verification_attempt"),
        ]
        assert result == {"attempt_id": "a-1", "outcome": "server_error"}

    def test_verify_failure_terminalizes(self) -> None:
        payload = _prepared_payload(
            repo_fork_requirement(slug="fork", required_repo="owner/repo"),
            "https://github.com/alice/repo",
        )
        ctx = _FakeOrchestrationContext({"attempt_id": "a-1"})
        responder = _make_responder(
            payload, fail_activity="execute_requirement_verification"
        )
        calls, _ = _drive(function_app._run_attempt_orchestration(ctx), responder)
        assert _sequence(calls) == [
            ("activity_with_retry", "prepare_verification_attempt"),
            ("activity_with_retry", "execute_requirement_verification"),
            ("activity_with_retry", "terminalize_verification_attempt"),
        ]


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


class TestReconciler:
    pytestmark = pytest.mark.asyncio

    async def test_maps_statuses_and_skips_healthy(self) -> None:
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
        assert _CapturingRepo.captured_cutoff == stale_cutoff(now, 30)

        terminalized = {
            call.args[0]: call.kwargs["outcome"] for call in term.await_args_list
        }
        assert terminalized[failed] is VerificationAttemptOutcome.SERVER_ERROR
        assert terminalized[terminated] is VerificationAttemptOutcome.CANCELLED
        assert terminalized[completed] is VerificationAttemptOutcome.SERVER_ERROR
        assert terminalized[missing] is VerificationAttemptOutcome.SERVER_ERROR
        assert running not in terminalized

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
        term.assert_not_awaited()


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
