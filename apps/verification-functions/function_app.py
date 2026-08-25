"""Durable Functions host for asynchronous verification attempts."""

from __future__ import annotations

import asyncio
import atexit
import json
import logging
import os
from collections.abc import Iterator, Mapping, Sequence
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from uuid import UUID

import azure.durable_functions as df
import azure.functions as func
from learn_to_cloud_shared.core.config import get_worker_settings
from learn_to_cloud_shared.core.database import create_engine, create_session_maker
from learn_to_cloud_shared.core.logger import (
    APP_LOGGER_NAMESPACE,
    configure_logging,
    remove_app_stdout_handler,
)
from learn_to_cloud_shared.core.observability import (
    configure_dependency_instrumentation,
    configure_otlp_observability,
)
from learn_to_cloud_shared.models import utcnow
from learn_to_cloud_shared.repositories.verification_attempt_repository import (
    AttemptTerminalState,
    VerificationAttemptRepository,
)
from learn_to_cloud_shared.verification_attempt_executor import (
    finalize_verification_attempt as finalize_attempt,
)
from learn_to_cloud_shared.verification_attempt_executor import (
    prepare_verification_attempt as prepare_attempt,
)
from learn_to_cloud_shared.verification_attempt_executor import (
    terminalize_verification_attempt as terminalize_attempt,
)
from learn_to_cloud_shared.verification_attempt_reconciler import (
    reconcile_decision,
    stale_cutoff,
)
from learn_to_cloud_shared.verification.llm_grading import (
    LLMGradingDecisionPayload,
    LLMGradingRequest,
    llm_grading_content_filtered_result,
    llm_grading_unavailable_result,
)
from learn_to_cloud_shared.verification.llm_grading import (
    apply_llm_grading_decisions as apply_llm_decisions,
)
from learn_to_cloud_shared.verification.engine import run_profile
from learn_to_cloud_shared.verification_workflow import (
    LLM_ERROR_TYPES,
    PreparedVerificationAttempt,
    VerificationRunResult,
)
from opentelemetry import context as otel_context
from opentelemetry.propagate import extract
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker
from verification_agents import (
    ContentFilteredError,
    LLM_OUTCOME_CONTENT_FILTERED,
    LLM_OUTCOME_ERROR,
    LLM_OUTCOME_SUCCESS,
    LLMGradingError,
    grade_evidence,
    missing_grading_config,
)


def _python_worker_telemetry_enabled() -> bool:
    return (
        os.getenv("PYTHON_APPLICATIONINSIGHTS_ENABLE_TELEMETRY", "").strip().lower()
        == "true"
    )


def _configure_function_telemetry() -> None:
    configure_logging()
    logging.getLogger(APP_LOGGER_NAMESPACE).setLevel(logging.INFO)
    for logger_name in ("azure.functions", "proxy_worker"):
        logging.getLogger(logger_name).setLevel(logging.WARNING)

    if _python_worker_telemetry_enabled():
        configure_dependency_instrumentation()
        return
    if configure_otlp_observability():
        remove_app_stdout_handler()


_configure_function_telemetry()

logger = logging.getLogger(f"{APP_LOGGER_NAMESPACE}.verification_functions")

app = df.DFApp(http_auth_level=func.AuthLevel.ANONYMOUS)

_ATTEMPT_ORCHESTRATOR_NAME = "verification_attempt_orchestrator_v1"
_VERIFY_RETRY_OPTIONS = df.RetryOptions(
    first_retry_interval_in_milliseconds=5000,
    max_number_of_attempts=3,
)
_TRANSIENT_RETRY_OPTIONS = df.RetryOptions(
    first_retry_interval_in_milliseconds=2000,
    max_number_of_attempts=3,
)
_engine: AsyncEngine | None = None
_session_maker: async_sessionmaker[AsyncSession] | None = None


def _get_session_maker() -> async_sessionmaker[AsyncSession]:
    global _engine, _session_maker
    if _session_maker is None:
        _engine = create_engine(get_worker_settings().database)
        _session_maker = create_session_maker(_engine)
    return _session_maker


@atexit.register
def _dispose_engine_on_exit() -> None:
    if _engine is None:
        return
    try:
        asyncio.run(_engine.dispose())
    except RuntimeError:
        logger.debug("verification.engine.dispose_skipped", exc_info=True)


def _trace_context_carrier(context: func.Context | None) -> dict[str, str]:
    if context is None:
        return {}

    trace_context = context.trace_context
    carrier: dict[str, str] = {}
    if trace_context.trace_parent:
        carrier["traceparent"] = trace_context.trace_parent
    if trace_context.trace_state:
        carrier["tracestate"] = trace_context.trace_state
    return carrier


@contextmanager
def _attached_invocation_context(context: func.Context | None) -> Iterator[None]:
    carrier = _trace_context_carrier(context)
    if not carrier:
        yield
        return

    token = otel_context.attach(extract(carrier))
    try:
        yield
    finally:
        otel_context.detach(token)


def _json_response(
    payload: Mapping[str, object], status_code: int
) -> func.HttpResponse:
    return func.HttpResponse(
        json.dumps(dict(payload), default=str),
        status_code=status_code,
        mimetype="application/json",
    )


def _activity_payload(value: object) -> dict[str, object]:
    if not isinstance(value, Mapping):
        raise TypeError("Expected Durable activity payload object")
    payload: dict[str, object] = {}
    for key, item in value.items():
        if not isinstance(key, str):
            raise TypeError("Expected Durable activity payload string keys")
        payload[key] = item
    return payload


def _activity_payloads(value: object) -> list[dict[str, object]]:
    if not isinstance(value, list):
        raise TypeError("Expected Durable activity payload list")
    return [_activity_payload(item) for item in value]


def _safe_llm_error_type(value: object) -> str:
    """Return a whitelisted LLM error category."""
    if isinstance(value, str) and value in LLM_ERROR_TYPES:
        return value
    return "llm.unknown"


def _attempt_custom_status(
    step: str,
    attempt_id: object,
    attempt: PreparedVerificationAttempt,
) -> dict[str, object]:
    return {
        "step": step,
        "attempt_id": attempt_id,
        "requirement_slug": attempt.requirement.slug,
        "submission_type": attempt.requirement.submission_type.value,
    }


def _result_custom_status(
    step: str,
    attempt_id: object,
    result: Mapping[str, object],
) -> dict[str, object]:
    status: dict[str, object] = {"step": step, "attempt_id": attempt_id}
    for key in ("phase_id", "requirement_slug", "submission_type"):
        value = result.get(key)
        if value is not None:
            status[key] = value
    return status


@dataclass(frozen=True)
class _PreparedOutcome:
    """Preparation produced an attempt ready for verification."""

    attempt_id: str
    prepared_payload: Mapping[str, object]
    prepared_attempt: PreparedVerificationAttempt


def _verify_step(context: df.DurableOrchestrationContext, outcome: _PreparedOutcome):
    """Run the requirement verification activity and return its run result."""
    context.set_custom_status(
        _attempt_custom_status(
            "verifying", outcome.attempt_id, outcome.prepared_attempt
        )
    )
    run_result = yield context.call_activity_with_retry(
        "execute_requirement_verification",
        _VERIFY_RETRY_OPTIONS,
        outcome.prepared_payload,
    )
    return run_result


def _llm_grading_step(
    context: df.DurableOrchestrationContext,
    outcome: _PreparedOutcome,
    run_result: object,
):
    """Apply LLM rubric grading when the run produced grading requests.

    Every profile records its grading requests on the verify result
    (``grading_requests`` is a list, possibly empty); the orchestrator grades
    exactly those. Deterministic types record an empty list (or omit the key),
    so grading is skipped and the run result passes through unchanged.
    """
    llm_requests: Sequence[object] = []
    if isinstance(run_result, Mapping):
        value = _activity_payload(run_result).get("grading_requests")
        if isinstance(value, list):
            llm_requests = value
    if not llm_requests:
        return run_result

    context.set_custom_status(
        _attempt_custom_status(
            "llm_grading", outcome.attempt_id, outcome.prepared_attempt
        )
    )
    config_status = yield context.call_activity("ensure_grading_config", None)
    if not config_status.get("valid"):
        return (
            yield context.call_activity(
                "llm_grading_failed",
                {"run_result": run_result, "error_type": "llm.configuration"},
            )
        )

    decisions: list[dict[str, object]] = []
    for request_payload in llm_requests:
        grading_result = yield context.call_activity(
            "run_llm_grading",
            {"request": request_payload},
        )
        result_payload = _activity_payload(grading_result)
        technical_outcome = result_payload.get("outcome")
        if technical_outcome != LLM_OUTCOME_SUCCESS:
            error_type = _safe_llm_error_type(result_payload.get("error_type"))
            return (
                yield context.call_activity(
                    "llm_grading_failed",
                    {
                        "run_result": run_result,
                        "error_type": error_type,
                        "outcome": technical_outcome,
                    },
                )
            )
        decisions.append(_activity_payload(result_payload["decision"]))

    return (
        yield context.call_activity(
            "apply_llm_grading_results",
            {"run_result": run_result, "decisions": decisions},
        )
    )


@app.activity_trigger(input_name="job_payload")
async def execute_requirement_verification(
    job_payload,
    context: func.Context,
) -> dict[str, object]:
    """Run the requirement verifier without writing database state."""
    with _attached_invocation_context(context):
        prepared_attempt = PreparedVerificationAttempt.from_payload(
            _activity_payload(job_payload)
        )
        run_result = await run_profile(prepared_attempt)
        return run_result.to_payload()


@app.activity_trigger(input_name="payload")
async def ensure_grading_config(
    payload,
    context: func.Context,
) -> dict[str, object]:
    """Report whether the Foundry grading config is present.

    Missing config is a permanent deployment error, not a transient fault,
    so the orchestrator runs this once without retries and fails the job
    fast instead of retrying the grading activity four times.
    """
    with _attached_invocation_context(context):
        missing = missing_grading_config()
        return {"valid": not missing, "missing_vars": missing}


@app.activity_trigger(input_name="request_payload")
async def run_llm_grading(
    request_payload,
    context: func.Context,
) -> dict[str, object]:
    """Call Foundry for one LLM grading request and return durable-safe JSON."""
    with _attached_invocation_context(context):
        data = _activity_payload(request_payload)
        request = LLMGradingRequest.model_validate(_activity_payload(data["request"]))
        try:
            decision = await grade_evidence(request.message)
        except LLMGradingError as exc:
            return {
                "outcome": LLM_OUTCOME_ERROR,
                "error_type": exc.error_type,
            }
        except ContentFilteredError:
            return {"outcome": LLM_OUTCOME_CONTENT_FILTERED}
        return {
            "outcome": LLM_OUTCOME_SUCCESS,
            "decision": LLMGradingDecisionPayload(
                task=request.task,
                decision=decision,
            ).model_dump(mode="json"),
        }


@app.activity_trigger(input_name="payload")
async def apply_llm_grading_results(
    payload,
    context: func.Context,
) -> dict[str, object]:
    """Merge durable LLM grading decisions into the verifier output."""
    with _attached_invocation_context(context):
        data = _activity_payload(payload)
        run_payload = _activity_payload(data["run_result"])
        run_result_payload = VerificationRunResult.from_payload(run_payload)
        decision_payloads = [
            LLMGradingDecisionPayload.model_validate(item)
            for item in _activity_payloads(data["decisions"])
        ]
        run_result = apply_llm_decisions(
            run_result_payload,
            decision_payloads,
        )
        return run_result.to_payload()


@app.activity_trigger(input_name="payload")
async def llm_grading_failed(
    payload,
    context: func.Context,
) -> dict[str, object]:
    """Convert LLM grader errors into a persisted server-error result."""
    with _attached_invocation_context(context):
        data = _activity_payload(payload)
        error_type = _safe_llm_error_type(data.get("error_type"))
        technical_outcome = data.get("outcome")
        run_result_payload = VerificationRunResult.from_payload(
            _activity_payload(data["run_result"])
        )
        if technical_outcome == LLM_OUTCOME_CONTENT_FILTERED:
            run_result = llm_grading_content_filtered_result(run_result_payload)
        else:
            logger.error(
                "verification.llm_grading.failed",
                extra={"error.type": error_type},
            )
            run_result = llm_grading_unavailable_result(
                run_result_payload,
                error_type=error_type,
            )
        return run_result.to_payload()


@app.route(route="verification/attempts/{instance_id}/status", methods=["GET"])
@app.durable_client_input(client_name="client")
async def get_verification_attempt_status(
    req: func.HttpRequest,
    client: df.DurableOrchestrationClient,
    context: func.Context,
) -> func.HttpResponse:
    """Return minimal Durable status for a verification attempt."""
    with _attached_invocation_context(context):
        raw_instance_id = req.route_params.get("instance_id")
        if raw_instance_id is None:
            return _json_response({"error": "missing_instance_id"}, status_code=400)

        try:
            instance_id = str(UUID(raw_instance_id))
        except ValueError:
            return _json_response({"error": "invalid_instance_id"}, status_code=400)

        status = await client.get_status(
            instance_id,
            show_history=False,
            show_history_output=False,
            show_input=False,
        )
        if status is None:
            return _json_response({"error": "instance_not_found"}, status_code=404)

        return _json_response(status.to_json(), status_code=200)


# ---------------------------------------------------------------------------
# Verification-attempt workflow
#
# The
# Durable input carries only the attempt id; every trusted field is loaded
# from the attempt row by the prepare activity. Verification and LLM grading
# reuse the shared activities. Terminal state is written with a
# compare-and-set finalize, and any authoritative failure is converted into a
# terminal outcome via the terminalize activity instead of relying on polling.
# ---------------------------------------------------------------------------


def _attempt_id_from_input(context: df.DurableOrchestrationContext) -> str:
    input_payload = context.get_input()
    if not isinstance(input_payload, Mapping):
        raise TypeError(
            f"verification attempt orchestration: expected Mapping input, "
            f"got {type(input_payload).__name__}"
        )
    attempt_id = input_payload.get("attempt_id")
    if not isinstance(attempt_id, str):
        raise TypeError("verification attempt orchestration: missing attempt_id")
    return attempt_id


def _finalize_attempt_step(
    context: df.DurableOrchestrationContext,
    outcome: _PreparedOutcome,
    run_result: object,
):
    """Persist the attempt's terminal outcome via the CAS finalize activity."""
    context.set_custom_status(
        _attempt_custom_status(
            "finalizing", outcome.attempt_id, outcome.prepared_attempt
        )
    )
    result = yield context.call_activity_with_retry(
        "finalize_verification_attempt",
        _TRANSIENT_RETRY_OPTIONS,
        run_result,
    )
    result_payload = _activity_payload(result)
    context.set_custom_status(
        _result_custom_status("completed", outcome.attempt_id, result_payload)
    )
    return result


def _terminalize_attempt_step(
    context: df.DurableOrchestrationContext,
    attempt_id: str,
    failure_stage: str,
):
    """Convert an authoritative orchestration failure into a terminal outcome.

    Runs the terminalize activity so an exhausted-retry activity failure or an
    orchestrator error records a trustworthy ``server_error`` instead of
    leaving the attempt active for a browser poll that will never resolve it.
    """
    context.set_custom_status({"step": "terminalizing", "attempt_id": attempt_id})
    return (
        yield context.call_activity_with_retry(
            "terminalize_verification_attempt",
            _TRANSIENT_RETRY_OPTIONS,
            {
                "attempt_id": attempt_id,
                "outcome": "server_error",
                "error_code": "server_error",
                "validation_message": "Verification could not be completed.",
                "terminal_source": f"orchestrator_{failure_stage}_exception",
            },
        )
    )


def _run_attempt_orchestration(context: df.DurableOrchestrationContext):
    """Versioned workflow: prepare -> verify -> grade -> finalize.

    Prepare loads and validates the attempt row (payload version, snapshot
    provenance/hash, value kind, active state) and returns a runnable attempt
    the verify/grade steps consume. Any exception in the
    authoritative path terminalizes the attempt instead of failing silently.

    Kept as a plain generator (separate from the decorated trigger) so the
    orchestration tests can drive it directly.
    """
    attempt_id = _attempt_id_from_input(context)
    context.set_custom_status({"step": "preparing", "attempt_id": attempt_id})
    failure_stage = "prepare"
    try:
        preparation = yield context.call_activity_with_retry(
            "prepare_verification_attempt",
            _TRANSIENT_RETRY_OPTIONS,
            {"attempt_id": attempt_id},
        )
        prepared_attempt_payload = preparation["attempt"]
        prepared_attempt = PreparedVerificationAttempt.from_payload(
            _activity_payload(prepared_attempt_payload)
        )
        outcome = _PreparedOutcome(
            attempt_id=attempt_id,
            prepared_payload=prepared_attempt_payload,
            prepared_attempt=prepared_attempt,
        )
        failure_stage = "verification"
        run_result = yield from _verify_step(context, outcome)
        failure_stage = "grading"
        run_result = yield from _llm_grading_step(context, outcome, run_result)
        failure_stage = "finalization"
        return (yield from _finalize_attempt_step(context, outcome, run_result))
    except Exception:
        yield from _terminalize_attempt_step(context, attempt_id, failure_stage)
        raise


@app.orchestration_trigger(context_name="context")
def verification_attempt_orchestrator_v1(context: df.DurableOrchestrationContext):
    """Run the versioned unified verification-attempt workflow."""
    return (yield from _run_attempt_orchestration(context))


def _terminal_state_payload(state: AttemptTerminalState) -> dict[str, object]:
    return {
        "attempt_id": str(state.id),
        "outcome": state.outcome,
        "error_code": state.error_code,
        "validation_message": state.validation_message,
        "terminal_source": state.terminal_source,
        "completed_at": state.completed_at.isoformat()
        if state.completed_at is not None
        else None,
    }


@app.activity_trigger(input_name="input_payload")
async def prepare_verification_attempt(
    input_payload,
    context: func.Context,
) -> dict[str, object]:
    """Load and validate an attempt row for verification."""
    with _attached_invocation_context(context):
        data = _activity_payload(input_payload)
        raw_attempt_id = data.get("attempt_id")
        if not isinstance(raw_attempt_id, str):
            raise TypeError("prepare_verification_attempt: missing attempt_id")
        attempt_id = UUID(raw_attempt_id)
        preparation = await prepare_attempt(
            attempt_id,
            session_maker=_get_session_maker(),
        )
        return preparation.to_payload()


@app.activity_trigger(input_name="run_payload")
async def finalize_verification_attempt(
    run_payload,
    context: func.Context,
) -> dict[str, object]:
    """Compare-and-set the attempt's real outcome."""
    with _attached_invocation_context(context):
        run_result = VerificationRunResult.from_payload(_activity_payload(run_payload))
        result = await finalize_attempt(
            run_result,
            session_maker=_get_session_maker(),
        )
        state = result.state
        return _terminal_state_payload(state)


@app.activity_trigger(input_name="input_payload")
async def terminalize_verification_attempt(
    input_payload,
    context: func.Context,
) -> dict[str, object]:
    """Compare-and-set a failure/cancellation outcome."""
    with _attached_invocation_context(context):
        data = _activity_payload(input_payload)
        attempt_id = UUID(str(data["attempt_id"]))
        result = await terminalize_attempt(
            attempt_id,
            outcome=str(data["outcome"]),
            error_code=str(data["error_code"]),
            validation_message=str(data["validation_message"]),
            terminal_source=str(data["terminal_source"]),
            session_maker=_get_session_maker(),
        )
        state = result.state
        return _terminal_state_payload(state)


def _durable_instance_exists(status: object) -> bool:
    """True when a Durable status describes a real, existing instance."""
    if status is None:
        return False
    return getattr(status, "runtime_status", None) is not None


def _runtime_status_name(status: object) -> str | None:
    """Return a Durable status's runtime-status name, or None when absent."""
    if status is None:
        return None
    runtime_status = getattr(status, "runtime_status", None)
    if runtime_status is None:
        return None
    return getattr(runtime_status, "name", str(runtime_status))


class _StartOutcome(Enum):
    """Result of an idempotent attempt-orchestration start."""

    STARTED = "started"
    ALREADY_EXISTS = "already_exists"
    ALREADY_CLAIMED = "already_claimed"
    AMBIGUOUS_STARTED = "ambiguous_started"
    START_FAILED = "start_failed"
    ATTEMPT_NOT_FOUND = "attempt_not_found"


class _StartClaim(Enum):
    """Database claim state before any Durable start call."""

    CLAIMED = "claimed"
    ALREADY_CLAIMED = "already_claimed"
    TERMINAL = "terminal"
    MISSING = "missing"


async def _get_instance_status(
    client: df.DurableOrchestrationClient, instance_id: str
) -> object:
    return await client.get_status(
        instance_id,
        show_history=False,
        show_history_output=False,
        show_input=False,
    )


async def _resolve_ambiguous_start(
    client: df.DurableOrchestrationClient,
    instance_id: str,
) -> object | None:
    """Poll briefly until Durable confirms the instance exists or is absent."""
    all_queries_succeeded = True
    for delay_seconds in (0.0, 0.5, 1.5):
        if delay_seconds:
            await asyncio.sleep(delay_seconds)
        try:
            status = await _get_instance_status(client, instance_id)
        except Exception:
            all_queries_succeeded = False
            logger.exception(
                "verification.attempt.start.status_query_failed",
                extra={"attempt_id": instance_id},
            )
            continue
        if _durable_instance_exists(status):
            return status
    if not all_queries_succeeded:
        raise RuntimeError(
            f"Durable status could not confirm whether attempt {instance_id} started"
        )
    return None


async def _claim_attempt_start(
    attempt_id: UUID,
    *,
    session_maker: async_sessionmaker[AsyncSession],
) -> _StartClaim:
    """Atomically claim the right to call Durable ``start_new``."""
    async with session_maker() as db:
        repo = VerificationAttemptRepository(db)
        if await repo.mark_started(attempt_id):
            await db.commit()
            return _StartClaim.CLAIMED

        status = await repo.get_status(attempt_id)
        if status is None:
            return _StartClaim.MISSING
        if status.outcome is not None:
            return _StartClaim.TERMINAL
        return _StartClaim.ALREADY_CLAIMED


async def _start_attempt_orchestration(
    client: df.DurableOrchestrationClient,
    attempt_uuid: UUID,
    *,
    session_maker: async_sessionmaker[AsyncSession],
) -> _StartOutcome:
    """Idempotently start the attempt orchestration keyed by the attempt UUID.

    The attempt UUID is the Durable instance id, so a retry re-uses the same
    id. An already-existing instance is treated as success; an ambiguous start
    failure is resolved by inspecting Durable status before deciding the start
    truly failed; only a confirmed start failure terminalizes the attempt.
    """
    instance_id = str(attempt_uuid)

    claim = await _claim_attempt_start(
        attempt_uuid,
        session_maker=session_maker,
    )
    if claim is _StartClaim.MISSING:
        return _StartOutcome.ATTEMPT_NOT_FOUND
    if claim is _StartClaim.TERMINAL:
        return _StartOutcome.ALREADY_EXISTS
    if claim is _StartClaim.ALREADY_CLAIMED:
        existing = await _resolve_ambiguous_start(client, instance_id)
        if not _durable_instance_exists(existing):
            logger.info(
                "verification.attempt.start.claimed_pending",
                extra={"attempt_id": instance_id},
            )
            return _StartOutcome.ALREADY_CLAIMED
        logger.info(
            "verification.attempt.start.already_exists",
            extra={
                "attempt_id": instance_id,
                "runtime_status": _runtime_status_name(existing),
            },
        )
        return _StartOutcome.ALREADY_EXISTS

    try:
        await client.start_new(
            _ATTEMPT_ORCHESTRATOR_NAME,
            instance_id=instance_id,
            client_input={"attempt_id": instance_id},
        )
    except Exception as exc:
        # The start result is ambiguous (timeout / transient query failure).
        # Inspect Durable status before deciding it failed so a race where the
        # instance actually started is not double-counted as a failure.
        status = await _resolve_ambiguous_start(client, instance_id)
        if _durable_instance_exists(status):
            logger.warning(
                "verification.attempt.start.ambiguous_but_started",
                extra={
                    "attempt_id": instance_id,
                    "runtime_status": _runtime_status_name(status),
                },
            )
            return _StartOutcome.AMBIGUOUS_STARTED

        logger.error(
            "verification.attempt.start.failed",
            extra={"attempt_id": instance_id, "error_type": type(exc).__name__},
        )
        await terminalize_attempt(
            attempt_uuid,
            outcome="server_error",
            error_code="server_error",
            validation_message="Verification could not be started.",
            terminal_source="start_failure",
            session_maker=session_maker,
        )
        return _StartOutcome.START_FAILED

    logger.info(
        "verification.attempt.orchestration.started",
        extra={
            "attempt_id": instance_id,
            "orchestrator_name": _ATTEMPT_ORCHESTRATOR_NAME,
        },
    )
    return _StartOutcome.STARTED


@app.route(route="verification/attempts/{attempt_id}/start", methods=["POST"])
@app.durable_client_input(client_name="client")
async def start_verification_attempt(
    req: func.HttpRequest,
    client: df.DurableOrchestrationClient,
    context: func.Context,
) -> func.HttpResponse:
    """Start the versioned attempt orchestration, keyed by the attempt UUID."""
    with _attached_invocation_context(context):
        raw_attempt_id = req.route_params.get("attempt_id")
        if raw_attempt_id is None:
            return _json_response({"error": "missing_attempt_id"}, status_code=400)

        try:
            attempt_uuid = UUID(raw_attempt_id)
        except ValueError:
            return _json_response({"error": "invalid_attempt_id"}, status_code=400)

        instance_id = str(attempt_uuid)
        outcome = await _start_attempt_orchestration(
            client,
            attempt_uuid,
            session_maker=_get_session_maker(),
        )
        if outcome is _StartOutcome.START_FAILED:
            return _json_response({"error": "start_failed"}, status_code=500)
        if outcome is _StartOutcome.ATTEMPT_NOT_FOUND:
            return _json_response({"error": "attempt_not_found"}, status_code=404)
        return client.create_check_status_response(req, instance_id)


@dataclass(frozen=True)
class _ReconcileSummary:
    """Structured result of a reconciler pass, for logging + tests."""

    candidate_count: int
    terminalized_count: int
    stuck_count: int


async def _emit_stuck_if_active(
    attempt_id: UUID,
    *,
    durable_status: str | None,
    reason: str,
    cutoff: datetime,
    reference: datetime,
    session_maker: async_sessionmaker[AsyncSession],
) -> bool:
    """Emit a stuck event only after PostgreSQL confirms the row is still stale."""
    async with session_maker() as db:
        current = await VerificationAttemptRepository(db).get_status(attempt_id)
    if current is None or current.outcome is not None:
        return False
    age_anchor = current.started_at or current.created_at
    if age_anchor >= cutoff:
        return False

    logger.warning(
        "verification.attempt.stuck",
        extra={
            "attempt_id": str(attempt_id),
            "verification.attempt.id": str(attempt_id),
            "verification.failure.stage": "reconciliation",
            "verification.retryable": True,
            "durable_status": durable_status,
            "stuck_reason": reason,
            "attempt_age_seconds": int((reference - age_anchor).total_seconds()),
        },
    )
    return True


async def _reconcile_stale_attempts(
    client: df.DurableOrchestrationClient,
    *,
    session_maker: async_sessionmaker[AsyncSession],
    stale_attempt_min_age_minutes: int,
    batch_limit: int,
    now: datetime | None = None,
) -> _ReconcileSummary:
    """Terminalize abandoned active attempts older than the verification window.

    Asks Durable for each fixed instance's status and compare-and-set
    terminalizes only the confirmed abandoned/failed/terminated/cancelled/
    not-started ones; healthy Pending/Running instances are left untouched.
    Idempotent: a re-run re-applies harmless CAS no-ops.
    """
    reference = now if now is not None else utcnow()
    cutoff = stale_cutoff(reference, stale_attempt_min_age_minutes)
    async with session_maker() as db:
        stale = await VerificationAttemptRepository(db).list_active_older_than(
            cutoff,
            limit=batch_limit,
        )
    logger.info(
        "verification.reconciler.scan",
        extra={"candidate_count": len(stale), "cutoff": cutoff.isoformat()},
    )

    terminalized = 0
    stuck = 0
    for attempt in stale:
        instance_id = str(attempt.id)
        try:
            status = await _get_instance_status(client, instance_id)
        except Exception:
            logger.exception(
                "verification.reconciler.status_query_failed",
                extra={"attempt_id": instance_id},
            )
            stuck += await _emit_stuck_if_active(
                attempt.id,
                durable_status=None,
                reason="status_query_failed",
                cutoff=cutoff,
                reference=reference,
                session_maker=session_maker,
            )
            continue
        status_name = _runtime_status_name(status)
        decision = reconcile_decision(status_name)
        if decision is None:
            stuck += await _emit_stuck_if_active(
                attempt.id,
                durable_status=status_name,
                reason="active_beyond_limit",
                cutoff=cutoff,
                reference=reference,
                session_maker=session_maker,
            )
            continue
        if status_name is None:
            try:
                confirmed_status = await _get_instance_status(client, instance_id)
            except Exception:
                logger.exception(
                    "verification.reconciler.status_recheck_failed",
                    extra={"attempt_id": instance_id},
                )
                stuck += await _emit_stuck_if_active(
                    attempt.id,
                    durable_status=None,
                    reason="status_recheck_failed",
                    cutoff=cutoff,
                    reference=reference,
                    session_maker=session_maker,
                )
                continue
            confirmed_name = _runtime_status_name(confirmed_status)
            decision = reconcile_decision(confirmed_name)
            if decision is None:
                stuck += await _emit_stuck_if_active(
                    attempt.id,
                    durable_status=confirmed_name,
                    reason="active_beyond_limit",
                    cutoff=cutoff,
                    reference=reference,
                    session_maker=session_maker,
                )
                continue
            status_name = confirmed_name
        result = await terminalize_attempt(
            attempt.id,
            outcome=decision.outcome,
            error_code=decision.error_code,
            validation_message=decision.validation_message,
            terminal_source=decision.terminal_source,
            session_maker=session_maker,
        )
        if not result.won:
            continue
        terminalized += 1
        logger.info(
            "verification.reconciler.terminalized",
            extra={
                "attempt_id": str(attempt.id),
                "durable_status": status_name,
                "outcome": decision.outcome.value,
            },
        )

    logger.info(
        "verification.reconciler.completed",
        extra={
            "candidate_count": len(stale),
            "terminalized_count": terminalized,
            "stuck_count": stuck,
        },
    )
    return _ReconcileSummary(
        candidate_count=len(stale),
        terminalized_count=terminalized,
        stuck_count=stuck,
    )


@app.timer_trigger(
    arg_name="timer",
    schedule="0 */15 * * * *",
    run_on_startup=False,
    use_monitor=True,
)
@app.durable_client_input(client_name="client")
async def reconcile_stale_verification_attempts(
    timer: func.TimerRequest,
    client: df.DurableOrchestrationClient,
    context: func.Context,
) -> None:
    """Scheduled reconciler for abandoned active verification attempts."""
    with _attached_invocation_context(context):
        cfg = get_worker_settings().reconciler
        await _reconcile_stale_attempts(
            client,
            session_maker=_get_session_maker(),
            stale_attempt_min_age_minutes=cfg.stale_attempt_min_age_minutes,
            batch_limit=cfg.batch_limit,
        )
