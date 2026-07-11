"""Durable Functions host for asynchronous verification jobs."""

from __future__ import annotations

import asyncio
import atexit
import json
import logging
import os
from collections.abc import Iterator, Mapping, Sequence
from contextlib import contextmanager
from dataclasses import dataclass
from uuid import UUID

import azure.durable_functions as df
import azure.functions as func
from learn_to_cloud_shared.core.config import get_worker_settings
from learn_to_cloud_shared.core.database import create_engine, create_session_maker
from learn_to_cloud_shared.core.logger import APP_LOGGER_NAMESPACE, configure_logging
from learn_to_cloud_shared.core.observability import configure_observability
from learn_to_cloud_shared.repositories.verification_job_repository import (
    VerificationJobRepository,
)
from learn_to_cloud_shared.submission_values import submission_value_from_columns
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
from learn_to_cloud_shared.verification_job_executor import (
    PreparedVerificationJob,
    VerificationJobNotFoundError,
    VerificationRunResult,
)
from learn_to_cloud_shared.verification_job_executor import (
    persist_verification_result as persist_prepared_verification_result,
)
from learn_to_cloud_shared.verification_job_executor import (
    prepare_verification_job as prepare_persisted_verification_job,
)
from opentelemetry import context as otel_context
from opentelemetry import trace as otel_trace
from opentelemetry.propagate import extract
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker
from verification_agents import (
    CONTENT_FILTER_MARKER,
    grade_evidence,
    missing_grading_config,
)


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

app = df.DFApp(http_auth_level=func.AuthLevel.ANONYMOUS)

# Every submission type runs through this one orchestrator. Routing to the
# right steps happens inside the verify activity via the engine profile
# registry (verification/engine.py run_profile), and LLM grading is
# data-driven -- the grading step runs only when the verify step emits
# grading requests, so deterministic phases pass straight through.
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


def _set_verification_span_attributes(
    *,
    job_id: str,
    user_id: int | None = None,
    github_username: str | None = None,
    phase_id: int | None = None,
    requirement_slug: str | None = None,
    submission_type: str | None = None,
    status: str | None = None,
    result_submission_id: int | None = None,
) -> None:
    """Add verification identity to the current span when telemetry is enabled."""
    span = otel_trace.get_current_span()
    if not span.is_recording():
        return

    span.set_attribute("verification.job_id", job_id)
    if phase_id is not None:
        span.set_attribute("verification.phase_id", phase_id)
    if requirement_slug:
        span.set_attribute("verification.requirement_slug", requirement_slug)
    if submission_type:
        span.set_attribute("verification.submission_type", submission_type)
    if status:
        span.set_attribute("verification.status", status)
    if result_submission_id is not None:
        span.set_attribute("verification.result_submission_id", result_submission_id)
    if user_id is not None:
        user_id_text = str(user_id)
        span.set_attribute("enduser.id", user_id_text)
        span.set_attribute("app.user_id", user_id_text)
    if github_username:
        span.set_attribute("enduser.name", github_username)
        span.set_attribute("app.github_username", github_username)


def _set_prepared_job_span_attributes(job: PreparedVerificationJob) -> None:
    _set_verification_span_attributes(
        job_id=str(job.id),
        user_id=job.user_id,
        github_username=job.github_username,
        requirement_slug=job.requirement.slug,
        submission_type=job.requirement.submission_type.value,
    )


def _set_result_span_attributes(result: Mapping[str, object]) -> None:
    job_id = result.get("job_id")
    if not isinstance(job_id, str):
        return

    phase_id = result.get("phase_id")
    requirement_slug = result.get("requirement_slug")
    submission_type = result.get("submission_type")
    status = result.get("status")
    result_submission_id = result.get("submission_id")

    _set_verification_span_attributes(
        job_id=job_id,
        phase_id=phase_id if isinstance(phase_id, int) else None,
        requirement_slug=(
            requirement_slug if isinstance(requirement_slug, str) else None
        ),
        submission_type=submission_type if isinstance(submission_type, str) else None,
        status=status if isinstance(status, str) else None,
        result_submission_id=(
            result_submission_id if isinstance(result_submission_id, int) else None
        ),
    )


def _log_verification_job_completed(
    result: Mapping[str, object],
    job: PreparedVerificationJob,
) -> None:
    logger.info(
        "verification.job.completed",
        extra={
            "job_id": result.get("job_id"),
            "user_id": job.user_id,
            "github_username": job.github_username,
            "requirement_slug": job.requirement.slug,
            "submission_type": job.requirement.submission_type.value,
            "status": result.get("status"),
            "result_submission_id": result.get("submission_id"),
            "is_valid": result.get("is_valid"),
            "verification_completed": result.get("verification_completed"),
            "error_code": result.get("code"),
        },
    )


def _job_custom_status(
    step: str,
    job_id: object,
    job: PreparedVerificationJob,
) -> dict[str, object]:
    return {
        "step": step,
        "job_id": job_id,
        "requirement_slug": job.requirement.slug,
        "submission_type": job.requirement.submission_type.value,
    }


def _result_custom_status(
    step: str,
    job_id: object,
    result: Mapping[str, object],
) -> dict[str, object]:
    status: dict[str, object] = {"step": step, "job_id": job_id}
    for key in ("phase_id", "requirement_slug", "submission_type"):
        value = result.get(key)
        if value is not None:
            status[key] = value
    return status


@dataclass(frozen=True)
class _TerminalOutcome:
    """Preparation already decided the job's outcome; skip verification."""

    result: object


@dataclass(frozen=True)
class _PreparedOutcome:
    """Preparation produced a job ready for the verify/persist steps."""

    job_id: str
    prepared_payload: Mapping[str, object]
    prepared_job: PreparedVerificationJob


def _prepare_step(context: df.DurableOrchestrationContext):
    """Validate and prepare the job. Shared first step for every workflow.

    Yields the ``prepare_verification_job`` activity and returns either a
    :class:`_TerminalOutcome` (preparation already decided the result) or a
    :class:`_PreparedOutcome`. Side effects (span attributes, custom
    status) are kept in the order the canonical workflow has always used
    so in-flight jobs replay identically.
    """
    input_payload = context.get_input()
    if not isinstance(input_payload, Mapping):
        raise TypeError(
            f"verification orchestration: expected Mapping input, "
            f"got {type(input_payload).__name__}"
        )
    job_id_obj = input_payload.get("id")
    job_id = job_id_obj if isinstance(job_id_obj, str) else str(job_id_obj)
    _set_verification_span_attributes(job_id=job_id)
    context.set_custom_status({"step": "preparing", "job_id": job_id})
    preparation = yield context.call_activity_with_retry(
        "prepare_verification_job",
        _TRANSIENT_RETRY_OPTIONS,
        input_payload,
    )

    terminal_result = preparation.get("terminal_result")
    if terminal_result is not None:
        result_payload = _activity_payload(terminal_result)
        _set_result_span_attributes(result_payload)
        context.set_custom_status(
            _result_custom_status("completed", job_id, result_payload)
        )
        return _TerminalOutcome(result=terminal_result)

    prepared_job = preparation["job"]
    prepared_job_payload = _activity_payload(prepared_job)
    prepared_verification_job = PreparedVerificationJob.from_payload(
        prepared_job_payload
    )
    _set_prepared_job_span_attributes(prepared_verification_job)
    return _PreparedOutcome(
        job_id=job_id,
        prepared_payload=prepared_job,
        prepared_job=prepared_verification_job,
    )


def _verify_step(context: df.DurableOrchestrationContext, outcome: _PreparedOutcome):
    """Run the requirement verification activity and return its run result."""
    context.set_custom_status(
        _job_custom_status("verifying", outcome.job_id, outcome.prepared_job)
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
        _job_custom_status("llm_grading", outcome.job_id, outcome.prepared_job)
    )
    config_status = yield context.call_activity("ensure_grading_config", None)
    if not config_status.get("valid"):
        missing = config_status.get("missing_vars") or []
        return (
            yield context.call_activity(
                "llm_grading_failed",
                {
                    "run_result": run_result,
                    "detail": f"missing grading config: {', '.join(missing)}",
                    "error_type": "MissingGradingConfig",
                },
            )
        )

    try:
        decisions: list[dict[str, object]] = []
        for request_payload in llm_requests:
            decision_payload = yield context.call_activity_with_retry(
                "run_llm_grading",
                _LLM_RETRY_OPTIONS,
                request_payload,
            )
            decisions.append(_activity_payload(decision_payload))

        return (
            yield context.call_activity(
                "apply_llm_grading_results",
                {"run_result": run_result, "decisions": decisions},
            )
        )
    except Exception as exc:
        return (
            yield context.call_activity(
                "llm_grading_failed",
                {
                    "run_result": run_result,
                    "detail": str(exc),
                    "error_type": type(exc).__name__,
                },
            )
        )


def _persist_step(
    context: df.DurableOrchestrationContext,
    outcome: _PreparedOutcome,
    run_result: object,
):
    """Persist the final run result and mark the job completed."""
    context.set_custom_status(
        _job_custom_status("persisting", outcome.job_id, outcome.prepared_job)
    )
    result = yield context.call_activity_with_retry(
        "persist_verification_result",
        _TRANSIENT_RETRY_OPTIONS,
        run_result,
    )
    result_payload = _activity_payload(result)
    _set_result_span_attributes(result_payload)
    context.set_custom_status(
        _result_custom_status("completed", outcome.job_id, result_payload)
    )
    return result


def _run_verification_orchestration(context: df.DurableOrchestrationContext):
    """The verification workflow for every submission type.

    prepare -> verify -> grade -> persist. The LLM grading step is
    data-driven: it runs only when the verify step produced grading
    requests, so deterministic phases (which never emit grading requests)
    pass straight through it. Routing to the right validator happens inside
    the verify activity via the engine profile registry.

    Kept as a plain generator (separate from the decorated trigger) so the
    orchestration tests can drive it directly.
    """
    outcome = yield from _prepare_step(context)
    if isinstance(outcome, _TerminalOutcome):
        return outcome.result
    run_result = yield from _verify_step(context, outcome)
    run_result = yield from _llm_grading_step(context, outcome, run_result)
    return (yield from _persist_step(context, outcome, run_result))


@app.orchestration_trigger(context_name="context")
def verification_orchestrator(context: df.DurableOrchestrationContext):
    """Run the verification workflow for every submission type."""
    return (yield from _run_verification_orchestration(context))


@app.activity_trigger(input_name="input_payload")
async def prepare_verification_job(
    input_payload,
    context: func.Context,
) -> dict[str, object]:
    """Validate the persisted verification job and return the prepared
    work item for the orchestrator to run.

    Input is the :class:`PreparedVerificationJob` payload dict carried
    by the orchestration. The requirement definition + github_username
    snapshot travel with the orchestration so this activity never
    reads curriculum or users tables.
    """
    with _attached_invocation_context(context):
        if not isinstance(input_payload, Mapping):
            raise TypeError(
                f"prepare_verification_job: expected Mapping input, "
                f"got {type(input_payload).__name__}"
            )
        prepared_input = PreparedVerificationJob.from_payload(input_payload)
        job_id = str(prepared_input.id)
        _set_verification_span_attributes(job_id=job_id)
        try:
            preparation = await prepare_persisted_verification_job(
                job_id,
                session_maker=_get_session_maker(),
                prepared_input=prepared_input,
            )
        except VerificationJobNotFoundError:
            logger.warning("verification.job.not_found", extra={"job_id": job_id})
            raise

        if preparation.job is not None:
            _set_prepared_job_span_attributes(preparation.job)
        return preparation.to_payload()


@app.activity_trigger(input_name="job_payload")
async def execute_requirement_verification(
    job_payload,
    context: func.Context,
) -> dict[str, object]:
    """Run the requirement verifier without writing database state."""
    with _attached_invocation_context(context):
        prepared_job = PreparedVerificationJob.from_payload(
            _activity_payload(job_payload)
        )
        _set_prepared_job_span_attributes(prepared_job)
        run_result = await run_profile(prepared_job)
        span = otel_trace.get_current_span()
        if span.is_recording():
            span.set_attribute(
                "verification.is_valid", run_result.validation_result.is_valid
            )
            span.set_attribute(
                "verification.completed",
                run_result.validation_result.verification_completed,
            )
        result_payload = run_result.to_payload()
        _set_result_span_attributes(result_payload)
        return result_payload


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
        request = LLMGradingRequest.model_validate(_activity_payload(request_payload))
        span = otel_trace.get_current_span()
        if span.is_recording():
            span.set_attribute("verification.llm_thread_id", request.thread_id)
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
        run_result_payload = VerificationRunResult.from_payload(run_payload)
        _set_prepared_job_span_attributes(run_result_payload.job)
        decision_payloads = [
            LLMGradingDecisionPayload.model_validate(item)
            for item in _activity_payloads(data["decisions"])
        ]
        run_result = apply_llm_decisions(
            run_result_payload,
            decision_payloads,
        )
        result_payload = run_result.to_payload()
        _set_result_span_attributes(result_payload)
        return result_payload


def _is_content_filter_failure(error_type: str, detail: str) -> bool:
    """Classify a grading failure as an Azure content-safety block.

    Durable Functions may deliver the activity error to the orchestrator as a
    wrapped exception, so the original type can be lost while the message text
    survives. Check both the type name and the detail for the stable marker.
    """
    return (
        error_type == "ContentFilteredError" or CONTENT_FILTER_MARKER in detail.lower()
    )


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
        error_type = data.get("error_type")
        if not isinstance(error_type, str) or not error_type:
            error_type = "unknown"
        run_result_payload = VerificationRunResult.from_payload(
            _activity_payload(data["run_result"])
        )
        _set_prepared_job_span_attributes(run_result_payload.job)
        # Record the real cause in telemetry so operators can diagnose the
        # failure. The user-facing result stays generic on purpose.
        span = otel_trace.get_current_span()
        if span.is_recording():
            span.set_attribute("verification.llm_grading_error_type", error_type)
            span.set_attribute("verification.llm_grading_error_detail", detail)
        logger.error(
            "verification.llm_grading.failed",
            extra={"error_type": error_type, "detail": detail},
        )
        if _is_content_filter_failure(error_type, detail):
            run_result = llm_grading_content_filtered_result(run_result_payload)
        else:
            run_result = llm_grading_unavailable_result(run_result_payload)
        result_payload = run_result.to_payload()
        _set_result_span_attributes(result_payload)
        return result_payload


@app.activity_trigger(input_name="run_payload")
async def persist_verification_result(
    run_payload,
    context: func.Context,
) -> dict[str, object]:
    """Persist the verification result and mark the job terminal."""
    with _attached_invocation_context(context):
        run_result = VerificationRunResult.from_payload(_activity_payload(run_payload))
        _set_prepared_job_span_attributes(run_result.job)
        result = await persist_prepared_verification_result(
            run_result,
            session_maker=_get_session_maker(),
        )
        result_payload = result.to_payload()
        _set_result_span_attributes(result_payload)
        _log_verification_job_completed(result_payload, run_result.job)
        return result_payload


@app.route(route="verification/jobs/{job_id}/start", methods=["POST"])
@app.durable_client_input(client_name="client")
async def start_verification_job(
    req: func.HttpRequest,
    client: df.DurableOrchestrationClient,
    context: func.Context,
) -> func.HttpResponse:
    """Start the verification orchestration for an existing job.

    The API posts a full :class:`PreparedVerificationJob` payload as
    the request body. We validate the immutable fields against the
    ``verification_jobs`` row (route ``job_id``, ``user_id``,
    ``requirement_uuid``, ``submitted_value``) so a leaked function
    key or API bug can't make us run validation against a forged
    user/requirement pair. The requirement *definition* and the
    ``github_username`` snapshot are trusted from the payload -- which
    is what lets the Functions role drop curriculum/users grants
    entirely.
    """
    with _attached_invocation_context(context):
        raw_job_id = req.route_params.get("job_id")
        if raw_job_id is None:
            return _json_response({"error": "missing_job_id"}, status_code=400)

        try:
            job_uuid = UUID(raw_job_id)
        except ValueError:
            return _json_response({"error": "invalid_job_id"}, status_code=400)

        try:
            body = req.get_json()
        except ValueError:
            return _json_response({"error": "invalid_json_body"}, status_code=400)

        try:
            prepared = PreparedVerificationJob.from_payload(body)
        except (KeyError, ValueError, TypeError) as exc:
            return _json_response(
                {"error": "invalid_payload", "detail": str(exc)},
                status_code=400,
            )

        if prepared.id != job_uuid:
            return _json_response({"error": "payload_job_id_mismatch"}, status_code=400)

        job_id = str(job_uuid)
        async with _get_session_maker()() as session:
            job = await VerificationJobRepository(session).get_by_id(job_uuid)
            if job is None:
                return _json_response({"error": "job_not_found"}, status_code=404)

            if (
                job.user_id != prepared.user_id
                or job.requirement_uuid != prepared.requirement.uuid
                or submission_value_from_columns(job) != prepared.typed_submitted_value
            ):
                return _json_response(
                    {"error": "payload_does_not_match_job"},
                    status_code=400,
                )

        submission_type_str = prepared.requirement.submission_type.value
        _set_verification_span_attributes(job_id=job_id)
        instance_id = await client.start_new(
            _ORCHESTRATOR_NAME,
            instance_id=job_id,
            client_input=prepared.to_payload(),
        )
        logger.info(
            "verification.orchestration.started",
            extra={
                "job_id": job_id,
                "instance_id": instance_id,
                "orchestrator_name": _ORCHESTRATOR_NAME,
                "requirement_slug": prepared.requirement.slug,
                "submission_type": submission_type_str,
            },
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
