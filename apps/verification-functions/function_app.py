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
from learn_to_cloud_shared.core.config import get_worker_settings
from learn_to_cloud_shared.core.database import create_engine, create_session_maker
from learn_to_cloud_shared.core.logger import APP_LOGGER_NAMESPACE, configure_logging
from learn_to_cloud_shared.core.observability import configure_observability
from learn_to_cloud_shared.models import SubmissionType
from learn_to_cloud_shared.repositories.verification_job_repository import (
    VerificationJobRepository,
)
from learn_to_cloud_shared.submission_values import submission_value_from_columns
from learn_to_cloud_shared.verification.llm_grading import (
    LLMGradingDecisionPayload,
    LLMGradingRequest,
    llm_grading_unavailable_result,
)
from learn_to_cloud_shared.verification.llm_grading import (
    apply_llm_grading_decisions as apply_llm_decisions,
)
from learn_to_cloud_shared.verification.llm_grading import (
    collect_llm_grading_requests as collect_llm_requests,
)
from learn_to_cloud_shared.verification_job_executor import (
    PreparedVerificationJob,
    VerificationJobNotFoundError,
    VerificationRunResult,
    run_verification,
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
from verification_agents import grade_evidence, missing_grading_config


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

_DEFAULT_ORCHESTRATOR_NAME = "verification_orchestrator"
# BACKGROUND submission types: phase 3+ verifications that involve LLM
# grading, multi-task fan-out, or external probes with retries and run on
# the Durable Functions path. The INLINE phase 0-2 types (github_profile,
# profile_readme, repo_fork, ctf_token, networking_token) run inside the
# FastAPI request instead and are intentionally absent. Execution mode is
# declared per type in verification/dispatcher.py (_VALIDATOR_REGISTRY);
# this map only picks the orchestrator name for the background types.
_ORCHESTRATOR_NAMES_BY_SUBMISSION_TYPE = {
    SubmissionType.JOURNAL_API_RESPONSE: "verify_phase3_journal_api_orchestrator",
    SubmissionType.CODE_ANALYSIS: "verify_phase3_journal_api_orchestrator",
    SubmissionType.PR_REVIEW: "verify_phase3_pr_review_orchestrator",
    SubmissionType.JOURNAL_API_VERIFIER: (
        "verify_phase3_journal_api_verifier_orchestrator"
    ),
    SubmissionType.DEPLOYED_API: "verify_phase4_deployed_api_orchestrator",
    SubmissionType.DEVOPS_ANALYSIS: "verify_phase5_devops_orchestrator",
    SubmissionType.SECURITY_SCANNING: "verify_phase6_security_orchestrator",
}
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


def _orchestrator_name_for_submission_type(submission_type: str) -> str:
    """Pick the Durable orchestrator for a verification's submission type.

    Phase D.3 dropped ``submission_type`` from ``verification_jobs``;
    callers resolve it via the linked requirement (see
    :func:`start_verification_job`).
    """
    try:
        enum_value = SubmissionType(submission_type)
    except ValueError:
        return _DEFAULT_ORCHESTRATOR_NAME
    return _ORCHESTRATOR_NAMES_BY_SUBMISSION_TYPE.get(
        enum_value,
        _DEFAULT_ORCHESTRATOR_NAME,
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


def _run_verification_orchestration(context: df.DurableOrchestrationContext):
    """Run one verification job workflow.

    Input is a :class:`PreparedVerificationJob` payload dict (with
    ``id``, ``requirement``, ``submitted_value`` etc.) -- the HTTP
    starter always builds and posts one. Functions never reads
    curriculum or users tables.
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
        return terminal_result

    prepared_job = preparation["job"]
    prepared_job_payload = _activity_payload(prepared_job)
    prepared_verification_job = PreparedVerificationJob.from_payload(
        prepared_job_payload
    )
    _set_prepared_job_span_attributes(prepared_verification_job)
    context.set_custom_status(
        _job_custom_status("verifying", job_id, prepared_verification_job)
    )
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
        context.set_custom_status(
            _job_custom_status("llm_grading", job_id, prepared_verification_job)
        )
        config_status = yield context.call_activity("ensure_grading_config", None)
        if not config_status.get("valid"):
            missing = config_status.get("missing_vars") or []
            run_result = yield context.call_activity(
                "llm_grading_failed",
                {
                    "run_result": run_result,
                    "detail": f"missing grading config: {', '.join(missing)}",
                    "error_type": "MissingGradingConfig",
                },
            )
        else:
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
                    {
                        "run_result": run_result,
                        "detail": str(exc),
                        "error_type": type(exc).__name__,
                    },
                )

    context.set_custom_status(
        _job_custom_status("persisting", job_id, prepared_verification_job)
    )
    result = yield context.call_activity_with_retry(
        "persist_verification_result",
        _TRANSIENT_RETRY_OPTIONS,
        run_result,
    )
    result_payload = _activity_payload(result)
    _set_result_span_attributes(result_payload)
    context.set_custom_status(
        _result_custom_status("completed", job_id, result_payload)
    )
    return result


@app.orchestration_trigger(context_name="context")
def verification_orchestrator(context: df.DurableOrchestrationContext):
    """Run the legacy generic verification workflow."""
    return (yield from _run_verification_orchestration(context))


@app.orchestration_trigger(context_name="context")
def verify_github_profile_orchestrator(context: df.DurableOrchestrationContext):
    """Drain-only orchestrator for in-flight phase 0 GitHub profile jobs.

    Phase 0-2 verifications now run synchronously in FastAPI (see
    ``api/src/learn_to_cloud/routes/htmx_routes.py``). This trigger stays
    registered so any orchestration started before the cutover can still
    complete cleanly. Safe to remove after Durable retention expires.
    """
    return (yield from _run_verification_orchestration(context))


@app.orchestration_trigger(context_name="context")
def verify_profile_readme_orchestrator(context: df.DurableOrchestrationContext):
    """Drain-only orchestrator for in-flight phase 0 profile README jobs.

    See :func:`verify_github_profile_orchestrator` for rationale.
    """
    return (yield from _run_verification_orchestration(context))


@app.orchestration_trigger(context_name="context")
def verify_repo_fork_orchestrator(context: df.DurableOrchestrationContext):
    """Drain-only orchestrator for in-flight phase 0 repo fork jobs.

    See :func:`verify_github_profile_orchestrator` for rationale.
    """
    return (yield from _run_verification_orchestration(context))


@app.orchestration_trigger(context_name="context")
def verify_ctf_token_orchestrator(context: df.DurableOrchestrationContext):
    """Drain-only orchestrator for in-flight phase 1 CTF token jobs.

    See :func:`verify_github_profile_orchestrator` for rationale.
    """
    return (yield from _run_verification_orchestration(context))


@app.orchestration_trigger(context_name="context")
def verify_networking_token_orchestrator(context: df.DurableOrchestrationContext):
    """Drain-only orchestrator for in-flight phase 2 networking token jobs.

    See :func:`verify_github_profile_orchestrator` for rationale.
    """
    return (yield from _run_verification_orchestration(context))


@app.orchestration_trigger(context_name="context")
def verify_phase3_journal_api_orchestrator(context: df.DurableOrchestrationContext):
    """Run Phase 3 journal API verification."""
    return ((yield from _run_verification_orchestration(context)),)


@app.orchestration_trigger(context_name="context")
def verify_phase3_pr_review_orchestrator(context: df.DurableOrchestrationContext):
    """Run Phase 3 pull request verification."""
    return (yield from _run_verification_orchestration(context))


@app.orchestration_trigger(context_name="context")
def verify_phase3_ci_status_orchestrator(context: df.DurableOrchestrationContext):
    """Drain-only orchestrator for in-flight phase 3 ci_status jobs.

    See :func:`verify_github_profile_orchestrator` for rationale.
    """
    return (yield from _run_verification_orchestration(context))


@app.orchestration_trigger(context_name="context")
def verify_phase3_journal_api_verifier_orchestrator(
    context: df.DurableOrchestrationContext,
):
    """Run Phase 3 journal API verification (CI gate + LLM rubric review)."""
    return (yield from _run_verification_orchestration(context))


@app.orchestration_trigger(context_name="context")
def verify_phase4_deployed_api_orchestrator(context: df.DurableOrchestrationContext):
    """Run Phase 4 deployed API verification."""
    return (yield from _run_verification_orchestration(context))


@app.orchestration_trigger(context_name="context")
def verify_phase5_devops_orchestrator(context: df.DurableOrchestrationContext):
    """Run Phase 5 DevOps verification."""
    return (yield from _run_verification_orchestration(context))


@app.orchestration_trigger(context_name="context")
def verify_phase6_security_orchestrator(context: df.DurableOrchestrationContext):
    """Run Phase 6 security verification."""
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
        run_result = await run_verification(prepared_job)
        result_payload = run_result.to_payload()
        _set_result_span_attributes(result_payload)
        return result_payload


@app.activity_trigger(input_name="run_payload")
async def collect_llm_grading_requests(
    run_payload,
    context: func.Context,
) -> list[dict[str, object]]:
    """Prepare durable LLM grading requests for the completed verifier output."""
    with _attached_invocation_context(context):
        run_result = VerificationRunResult.from_payload(_activity_payload(run_payload))
        _set_prepared_job_span_attributes(run_result.job)
        requests = await collect_llm_requests(run_result)
        return [request.model_dump(mode="json") for request in requests]


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
        orchestrator_name = _orchestrator_name_for_submission_type(submission_type_str)
        _set_verification_span_attributes(job_id=job_id)
        instance_id = await client.start_new(
            orchestrator_name,
            instance_id=job_id,
            client_input=prepared.to_payload(),
        )
        logger.info(
            "verification.orchestration.started",
            extra={
                "job_id": job_id,
                "instance_id": instance_id,
                "orchestrator_name": orchestrator_name,
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
