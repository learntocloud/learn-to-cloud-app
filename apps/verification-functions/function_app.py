"""Durable Functions host for asynchronous verification jobs."""

from __future__ import annotations

import asyncio
import atexit
import json
import logging
import os
from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from uuid import UUID

import azure.durable_functions as df
import azure.functions as func
from learn_to_cloud_shared.core.database import create_engine, create_session_maker
from learn_to_cloud_shared.core.logger import APP_LOGGER_NAMESPACE, configure_logging
from learn_to_cloud_shared.core.observability import configure_observability
from learn_to_cloud_shared.verification.llm_grading import (
    LLMGradingDecisionPayload,
    LLMGradingRequest,
    apply_llm_grading_decisions as apply_llm_decisions,
    collect_llm_grading_requests as collect_llm_requests,
    llm_grading_unavailable_result,
)
from learn_to_cloud_shared.verification_job_executor import (
    PreparedVerificationJob,
    VerificationJobNotFoundError,
    VerificationRunResult,
    persist_verification_result as persist_prepared_verification_result,
    prepare_verification_job as prepare_persisted_verification_job,
    run_verification,
)
from opentelemetry import context as otel_context
from opentelemetry.propagate import extract
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker
from verification_agents import grade_evidence


def _telemetry_destination_configured() -> bool:
    return bool(
        os.getenv("APPLICATIONINSIGHTS_CONNECTION_STRING")
        or os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT")
    )


def _configure_function_logging() -> None:
    if _telemetry_destination_configured():
        root = logging.getLogger()
        for handler in list(root.handlers):
            root.removeHandler(handler)
    else:
        configure_logging()

    logging.getLogger(APP_LOGGER_NAMESPACE).setLevel(logging.INFO)
    for logger_name in ("azure.functions", "proxy_worker"):
        logging.getLogger(logger_name).setLevel(logging.WARNING)


_configure_function_logging()

logger = logging.getLogger(f"{APP_LOGGER_NAMESPACE}.verification_functions")

configure_observability()

app = df.DFApp(http_auth_level=func.AuthLevel.FUNCTION)

_ORCHESTRATOR_NAME = "verification_orchestrator"
_VERIFY_RETRY_OPTIONS = df.RetryOptions(
    first_retry_interval_in_milliseconds=5000,
    max_number_of_attempts=3,
)
_TRANSIENT_RETRY_OPTIONS = df.RetryOptions(
    first_retry_interval_in_milliseconds=2000,
    max_number_of_attempts=3,
)
_LLM_RETRY_OPTIONS = df.RetryOptions(
    first_retry_interval_in_milliseconds=3000,
    max_number_of_attempts=4,
)

_engine: AsyncEngine | None = None
_session_maker: async_sessionmaker[AsyncSession] | None = None


def _get_session_maker() -> async_sessionmaker[AsyncSession]:
    global _engine, _session_maker
    if _session_maker is None:
        _engine = create_engine()
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


@app.orchestration_trigger(context_name="context")
def verification_orchestrator(context: df.DurableOrchestrationContext):
    """Run one verification job workflow."""
    job_id = context.get_input()
    context.set_custom_status({"step": "preparing", "job_id": job_id})
    preparation = yield context.call_activity_with_retry(
        "prepare_verification_job",
        _TRANSIENT_RETRY_OPTIONS,
        job_id,
    )

    terminal_result = preparation.get("terminal_result")
    if terminal_result is not None:
        context.set_custom_status({"step": "completed", "job_id": job_id})
        return terminal_result

    prepared_job = preparation["job"]
    context.set_custom_status({"step": "verifying", "job_id": job_id})
    run_result = yield context.call_activity_with_retry(
        "execute_requirement_verification",
        _VERIFY_RETRY_OPTIONS,
        prepared_job,
    )
    llm_requests = yield context.call_activity(
        "collect_llm_grading_requests",
        run_result,
    )
    if llm_requests:
        context.set_custom_status({"step": "llm_grading", "job_id": job_id})
        try:
            decisions: list[dict[str, object]] = []
            for request_payload in llm_requests:
                decision_payload = yield context.call_activity_with_retry(
                    "run_llm_grading",
                    _LLM_RETRY_OPTIONS,
                    request_payload,
                )
                decisions.append(_activity_payload(decision_payload))

            run_result = yield context.call_activity(
                "apply_llm_grading_results",
                {"run_result": run_result, "decisions": decisions},
            )
        except Exception as exc:
            run_result = yield context.call_activity(
                "llm_grading_failed",
                {"run_result": run_result, "detail": str(exc)},
            )

    context.set_custom_status({"step": "persisting", "job_id": job_id})
    result = yield context.call_activity_with_retry(
        "persist_verification_result",
        _TRANSIENT_RETRY_OPTIONS,
        run_result,
    )
    context.set_custom_status({"step": "completed", "job_id": job_id})
    return result


@app.activity_trigger(input_name="job_id")
async def prepare_verification_job(
    job_id: str,
    context: func.Context,
) -> dict[str, object]:
    """Load and mark the persisted verification job as running."""
    with _attached_invocation_context(context):
        try:
            preparation = await prepare_persisted_verification_job(
                job_id,
                session_maker=_get_session_maker(),
            )
        except VerificationJobNotFoundError:
            logger.warning("verification.job.not_found", extra={"job_id": job_id})
            raise

        return preparation.to_payload()


@app.activity_trigger(input_name="job_payload")
async def execute_requirement_verification(
    job_payload,
    context: func.Context,
) -> dict[str, object]:
    """Run the requirement verifier without writing database state."""
    with _attached_invocation_context(context):
        run_result = await run_verification(
            PreparedVerificationJob.from_payload(_activity_payload(job_payload)),
        )
        return run_result.to_payload()


@app.activity_trigger(input_name="run_payload")
async def collect_llm_grading_requests(
    run_payload,
    context: func.Context,
) -> list[dict[str, object]]:
    """Prepare durable LLM grading requests for the completed verifier output."""
    with _attached_invocation_context(context):
        requests = await collect_llm_requests(
            VerificationRunResult.from_payload(_activity_payload(run_payload))
        )
        return [request.model_dump(mode="json") for request in requests]


@app.activity_trigger(input_name="request_payload")
async def run_llm_grading(
    request_payload,
    context: func.Context,
) -> dict[str, object]:
    """Call Foundry for one LLM grading request and return durable-safe JSON."""
    with _attached_invocation_context(context):
        request = LLMGradingRequest.model_validate(_activity_payload(request_payload))
        decision = await grade_evidence(request.message)
        return LLMGradingDecisionPayload(
            task=request.task,
            decision=decision,
        ).model_dump(mode="json")


@app.activity_trigger(input_name="payload")
async def apply_llm_grading_results(
    payload,
    context: func.Context,
) -> dict[str, object]:
    """Merge durable LLM grading decisions into the verifier output."""
    with _attached_invocation_context(context):
        data = _activity_payload(payload)
        run_payload = _activity_payload(data["run_result"])
        decision_payloads = [
            LLMGradingDecisionPayload.model_validate(item)
            for item in _activity_payloads(data["decisions"])
        ]
        run_result = apply_llm_decisions(
            VerificationRunResult.from_payload(run_payload),
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
        detail = data.get("detail")
        if not isinstance(detail, str) or not detail:
            detail = "unknown_error"
        run_result = llm_grading_unavailable_result(
            VerificationRunResult.from_payload(_activity_payload(data["run_result"])),
            detail,
        )
        return run_result.to_payload()


@app.activity_trigger(input_name="run_payload")
async def persist_verification_result(
    run_payload,
    context: func.Context,
) -> dict[str, object]:
    """Persist the verification result and mark the job terminal."""
    with _attached_invocation_context(context):
        result = await persist_prepared_verification_result(
            VerificationRunResult.from_payload(_activity_payload(run_payload)),
            session_maker=_get_session_maker(),
        )
        return result.to_payload()


@app.route(route="verification/jobs/{job_id}/start", methods=["POST"])
@app.durable_client_input(client_name="client")
async def start_verification_job(
    req: func.HttpRequest,
    client: df.DurableOrchestrationClient,
    context: func.Context,
) -> func.HttpResponse:
    """Start the verification orchestration for an existing job."""
    with _attached_invocation_context(context):
        raw_job_id = req.route_params.get("job_id")
        if raw_job_id is None:
            return _json_response({"error": "missing_job_id"}, status_code=400)

        try:
            job_id = str(UUID(raw_job_id))
        except ValueError:
            return _json_response({"error": "invalid_job_id"}, status_code=400)

        instance_id = await client.start_new(
            _ORCHESTRATOR_NAME,
            instance_id=job_id,
            client_input=job_id,
        )
        logger.info(
            "verification.orchestration.started",
            extra={"job_id": job_id, "instance_id": instance_id},
        )
        return client.create_check_status_response(req, instance_id)


@app.route(route="verification/jobs/{instance_id}/status", methods=["GET"])
@app.durable_client_input(client_name="client")
async def get_verification_job_status(
    req: func.HttpRequest,
    client: df.DurableOrchestrationClient,
    context: func.Context,
) -> func.HttpResponse:
    """Return minimal Durable status for a verification orchestration."""
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
