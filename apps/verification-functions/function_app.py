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
from datetime import datetime
from enum import Enum
from uuid import UUID

import azure.durable_functions as df
import azure.functions as func
from learn_to_cloud_shared.core.config import get_worker_settings
from learn_to_cloud_shared.core.database import create_engine, create_session_maker
from learn_to_cloud_shared.core.logger import APP_LOGGER_NAMESPACE, configure_logging
from learn_to_cloud_shared.core.observability import configure_observability
from learn_to_cloud_shared.models import utcnow
from learn_to_cloud_shared.repositories.verification_attempt_repository import (
    AttemptTerminalState,
    VerificationAttemptRepository,
)
from learn_to_cloud_shared.repositories.verification_job_repository import (
    VerificationJobRepository,
)
from learn_to_cloud_shared.submission_values import submission_value_from_columns
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
# Versioned orchestrator for the unified ``verification_attempts`` path. Kept
# distinct from the legacy name so existing Durable history/replay for
# in-flight legacy instances is untouched; the attempt id is the instance id.
_ATTEMPT_ORCHESTRATOR_NAME = "verification_attempt_orchestrator_v1"
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


# ---------------------------------------------------------------------------
# Versioned unified verification-attempt path (bridge / PR4)
#
# Runs against the curriculum-decoupled ``verification_attempts`` table. The
# Durable input carries only the attempt id; every trusted field is loaded
# from the attempt row by the prepare activity. Verification and LLM grading
# reuse the legacy activities unchanged. Terminal state is written with a
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
        _job_custom_status("finalizing", outcome.job_id, outcome.prepared_job)
    )
    result = yield context.call_activity_with_retry(
        "finalize_verification_attempt",
        _TRANSIENT_RETRY_OPTIONS,
        run_result,
    )
    result_payload = _activity_payload(result)
    context.set_custom_status(
        _result_custom_status("completed", outcome.job_id, result_payload)
    )
    return result


def _terminalize_attempt_step(
    context: df.DurableOrchestrationContext,
    attempt_id: str,
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
                "terminal_source": "orchestrator_exception",
            },
        )
    )


def _run_attempt_orchestration(context: df.DurableOrchestrationContext):
    """Versioned workflow: prepare -> verify -> grade -> finalize.

    Prepare loads and validates the attempt row (payload version, snapshot
    provenance/hash, value kind, active state) and returns a runnable job the
    existing verify/grade steps consume unchanged. Any exception in the
    authoritative path terminalizes the attempt instead of failing silently.

    Kept as a plain generator (separate from the decorated trigger) so the
    orchestration tests can drive it directly.
    """
    attempt_id = _attempt_id_from_input(context)
    _set_verification_span_attributes(job_id=attempt_id)
    context.set_custom_status({"step": "preparing", "attempt_id": attempt_id})
    try:
        preparation = yield context.call_activity_with_retry(
            "prepare_verification_attempt",
            _TRANSIENT_RETRY_OPTIONS,
            {"attempt_id": attempt_id},
        )
        prepared_job_payload = preparation["job"]
        prepared_job = PreparedVerificationJob.from_payload(
            _activity_payload(prepared_job_payload)
        )
        _set_prepared_job_span_attributes(prepared_job)
        outcome = _PreparedOutcome(
            job_id=attempt_id,
            prepared_payload=prepared_job_payload,
            prepared_job=prepared_job,
        )
        run_result = yield from _verify_step(context, outcome)
        run_result = yield from _llm_grading_step(context, outcome, run_result)
        return (yield from _finalize_attempt_step(context, outcome, run_result))
    except Exception:
        return (yield from _terminalize_attempt_step(context, attempt_id))


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
    """Load + validate an attempt row and return a runnable job payload."""
    with _attached_invocation_context(context):
        data = _activity_payload(input_payload)
        raw_attempt_id = data.get("attempt_id")
        if not isinstance(raw_attempt_id, str):
            raise TypeError("prepare_verification_attempt: missing attempt_id")
        attempt_id = UUID(raw_attempt_id)
        _set_verification_span_attributes(job_id=str(attempt_id))
        preparation = await prepare_attempt(
            attempt_id,
            session_maker=_get_session_maker(),
        )
        _set_prepared_job_span_attributes(preparation.job)
        return preparation.to_payload()


@app.activity_trigger(input_name="run_payload")
async def finalize_verification_attempt(
    run_payload,
    context: func.Context,
) -> dict[str, object]:
    """Compare-and-set the attempt's real outcome."""
    with _attached_invocation_context(context):
        run_result = VerificationRunResult.from_payload(_activity_payload(run_payload))
        _set_prepared_job_span_attributes(run_result.job)
        state = await finalize_attempt(
            run_result,
            session_maker=_get_session_maker(),
        )
        logger.info(
            "verification.attempt.finalized",
            extra={"attempt_id": str(state.id), "outcome": state.outcome},
        )
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
        state = await terminalize_attempt(
            attempt_id,
            outcome=str(data["outcome"]),
            error_code=str(data["error_code"]),
            validation_message=str(data["validation_message"]),
            terminal_source=str(data["terminal_source"]),
            session_maker=_get_session_maker(),
        )
        logger.info(
            "verification.attempt.terminalized",
            extra={
                "attempt_id": str(state.id),
                "outcome": state.outcome,
                "terminal_source": state.terminal_source,
            },
        )
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
            extra={"attempt_id": instance_id, "error": str(exc)},
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
        _set_verification_span_attributes(job_id=instance_id)

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
    for attempt in stale:
        instance_id = str(attempt.id)
        try:
            status = await _get_instance_status(client, instance_id)
        except Exception:
            logger.exception(
                "verification.reconciler.status_query_failed",
                extra={"attempt_id": instance_id},
            )
            continue
        status_name = _runtime_status_name(status)
        decision = reconcile_decision(status_name)
        if decision is None:
            continue
        if status_name is None:
            try:
                confirmed_status = await _get_instance_status(client, instance_id)
            except Exception:
                logger.exception(
                    "verification.reconciler.status_recheck_failed",
                    extra={"attempt_id": instance_id},
                )
                continue
            confirmed_name = _runtime_status_name(confirmed_status)
            decision = reconcile_decision(confirmed_name)
            if decision is None:
                continue
            status_name = confirmed_name
        await terminalize_attempt(
            attempt.id,
            outcome=decision.outcome,
            error_code=decision.error_code,
            validation_message=decision.validation_message,
            terminal_source=decision.terminal_source,
            session_maker=session_maker,
        )
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
        },
    )
    return _ReconcileSummary(
        candidate_count=len(stale),
        terminalized_count=terminalized,
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
