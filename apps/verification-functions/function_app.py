"""Durable Functions host for asynchronous verification jobs."""

from __future__ import annotations

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

app = df.DFApp(http_auth_level=func.AuthLevel.FUNCTION)

_ORCHESTRATOR_NAME = "verification_orchestrator"
_VERIFY_RETRY_OPTIONS = df.RetryOptions(
    first_retry_interval_in_milliseconds=5000,
    max_number_of_attempts=3,
)

_engine: AsyncEngine | None = None
_session_maker: async_sessionmaker[AsyncSession] | None = None
_observability_configured = False


def _ensure_observability() -> None:
    global _observability_configured
    if _observability_configured:
        return
    configure_observability()
    _observability_configured = True


def _get_session_maker() -> async_sessionmaker[AsyncSession]:
    global _engine, _session_maker
    if _session_maker is None:
        _engine = create_engine()
        _session_maker = create_session_maker(_engine)
    return _session_maker


def _string_attr(value: object, *names: str) -> str | None:
    for name in names:
        attr = getattr(value, name, None)
        if isinstance(attr, str) and attr:
            return attr
    return None


def _trace_context_carrier(context: func.Context | None) -> dict[str, str]:
    if context is None:
        return {}

    trace_context = context.trace_context
    trace_parent = _string_attr(trace_context, "trace_parent", "Traceparent")
    trace_state = _string_attr(trace_context, "trace_state", "Tracestate")

    carrier: dict[str, str] = {}
    if trace_parent:
        carrier["traceparent"] = trace_parent
    if trace_state:
        carrier["tracestate"] = trace_state
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


def _json_response(payload: dict[str, object], status_code: int) -> func.HttpResponse:
    return func.HttpResponse(
        json.dumps(payload),
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


@app.orchestration_trigger(context_name="context")
def verification_orchestrator(context: df.DurableOrchestrationContext):
    """Run one verification job workflow."""
    job_id = context.get_input()
    context.set_custom_status({"step": "preparing", "job_id": job_id})
    preparation = yield context.call_activity("prepare_verification_job", job_id)

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

    context.set_custom_status({"step": "persisting", "job_id": job_id})
    result = yield context.call_activity("persist_verification_result", run_result)
    context.set_custom_status({"step": "completed", "job_id": job_id})
    return result


@app.activity_trigger(input_name="job_id")
async def prepare_verification_job(
    job_id: str,
    context: func.Context | None = None,
) -> dict[str, object]:
    """Load and mark the persisted verification job as running."""
    _ensure_observability()
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
    context: func.Context | None = None,
) -> dict[str, object]:
    """Run the requirement verifier without writing database state."""
    _ensure_observability()
    with _attached_invocation_context(context):
        run_result = await run_verification(
            PreparedVerificationJob.from_payload(_activity_payload(job_payload)),
        )
        return run_result.to_payload()


@app.activity_trigger(input_name="run_payload")
async def persist_verification_result(
    run_payload,
    context: func.Context | None = None,
) -> dict[str, object]:
    """Persist the verification result and mark the job terminal."""
    _ensure_observability()
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
    context: func.Context | None = None,
) -> func.HttpResponse:
    """Start the verification orchestration for an existing job."""
    _ensure_observability()
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
            job_id,
            job_id,
        )
        logger.info(
            "verification.orchestration.started",
            extra={"job_id": job_id, "instance_id": instance_id},
        )
        return client.create_check_status_response(req, instance_id)
