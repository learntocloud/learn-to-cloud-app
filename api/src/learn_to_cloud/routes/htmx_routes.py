"""HTMX routes — return HTML fragments for partial page updates.

These routes handle interactive HTMX requests (step toggles, form
submissions, etc.) and return HTML partials instead of JSON.

Async verifications use Durable Functions + SSE:
1. POST /htmx/github/submit — pre-validates and returns a spinner card
    immediately (~100ms)
2. Durable Functions runs verification and updates PostgreSQL job state
3. GET /htmx/verification/{requirement_id}/stream polls PostgreSQL and
   pushes the result HTML when the job reaches a terminal state
"""

import asyncio
import json
import logging
from dataclasses import dataclass
from typing import Annotated

from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse
from learn_to_cloud_shared.content_service import get_topic_by_id
from learn_to_cloud_shared.core.config import get_settings
from learn_to_cloud_shared.core.database import DbSession
from learn_to_cloud_shared.models import SubmissionType, VerificationJobStatus
from learn_to_cloud_shared.repositories.submission_repository import (
    SubmissionRepository,
)
from learn_to_cloud_shared.repositories.verification_job_repository import (
    ACTIVE_JOB_STATUSES,
    VerificationJobRepository,
)
from learn_to_cloud_shared.schemas import SubmissionData
from learn_to_cloud_shared.verification.execution import to_submission_data
from learn_to_cloud_shared.verification.requirements import get_requirement_by_id
from learn_to_cloud_shared.verification.url_derivation import (
    derive_submission_value,
    is_derivable,
)
from opentelemetry import trace
from starlette.responses import StreamingResponse

from learn_to_cloud.core.auth import CurrentUser, UserId
from learn_to_cloud.core.ratelimit import limiter
from learn_to_cloud.core.templates import templates
from learn_to_cloud.rendering.context import (
    build_progress_dict,
    build_requirement_card_context,
)
from learn_to_cloud.rendering.steps import build_step_data
from learn_to_cloud.services.durable_verification_client import (
    DurableVerificationConfigError,
    DurableVerificationStartError,
    start_verification_orchestration,
)
from learn_to_cloud.services.steps_service import (
    StepValidationError,
    complete_step,
    get_valid_completed_steps,
    parse_phase_id_from_topic_id,
    uncomplete_step,
)
from learn_to_cloud.services.submissions_service import (
    AlreadyValidatedError,
    DuplicatePrError,
    GitHubUsernameRequiredError,
    PriorPhaseNotCompleteError,
    RequirementNotFoundError,
    VerificationJobSubmission,
    create_verification_job,
)
from learn_to_cloud.services.users_service import (
    UserNotFoundError,
    delete_user_account,
    get_user_by_id,
)

logger = logging.getLogger(__name__)

# Submission errors whose message is safe to show directly to the user.
_USER_FACING_ERRORS = (
    AlreadyValidatedError,
    DuplicatePrError,
    GitHubUsernameRequiredError,
    PriorPhaseNotCompleteError,
    RequirementNotFoundError,
)

_DURABLE_START_ERROR_MESSAGE = (
    "Verification could not be started. This attempt was not counted — "
    "please try again."
)


@dataclass(frozen=True, slots=True)
class _VerificationStreamState:
    status: VerificationJobStatus
    error_message: str | None
    submission: SubmissionData | None


def _build_feedback_tasks_from_submission(
    submission: SubmissionData | None,
) -> tuple[list[dict[str, object]], int]:
    if submission is None or not submission.feedback_json:
        return [], 0

    try:
        raw_tasks = json.loads(submission.feedback_json)
    except (json.JSONDecodeError, TypeError):
        return [], 0

    tasks = [
        {
            "name": task.get("task_name", ""),
            "passed": task.get("passed", False),
            "message": task.get("feedback", ""),
            "next_steps": task.get("next_steps", ""),
        }
        for task in raw_tasks
        if isinstance(task, dict)
    ]
    return tasks, sum(1 for task in tasks if task["passed"])


async def _load_verification_stream_state(
    session_maker,
    user_id: int,
    requirement_id: str,
) -> _VerificationStreamState | None:
    async with session_maker() as session:
        job = await VerificationJobRepository(session).get_latest_for_requirement(
            user_id,
            requirement_id,
        )
        if job is None:
            return None

        submission = None
        if job.result_submission_id is not None:
            db_submission = await SubmissionRepository(session).get_by_id(
                job.result_submission_id
            )
            if db_submission is not None:
                submission = to_submission_data(db_submission)

        return _VerificationStreamState(
            status=job.status,
            error_message=job.error_message,
            submission=submission,
        )


router = APIRouter(prefix="/htmx", tags=["htmx"], include_in_schema=False)


async def _render_step_toggle(
    request: Request,
    db: DbSession,
    user_id: int,
    topic_id: str,
    step_id: str,
    phase_id: int,
) -> HTMLResponse:
    """Shared rendering for step complete/uncomplete HTMX responses.

    Looks up the step content and returns the combined step + progress
    HTML partials.
    """
    topic = get_topic_by_id(topic_id)
    step = None
    if topic:
        for s in topic.learning_steps:
            if s.id == step_id:
                step = s
                break

    if step is None:
        span = trace.get_current_span()
        span.add_event(
            "step_not_found",
            {"user_id": user_id, "topic_id": topic_id, "step_id": step_id},
        )
        return HTMLResponse("")

    assert topic is not None  # guaranteed: topic=None → step=None → early return
    step_data = build_step_data(step)
    user = await get_user_by_id(db, user_id)
    completed_steps = await get_valid_completed_steps(db, user_id, topic)

    total_steps = len(topic.learning_steps)
    progress = build_progress_dict(len(completed_steps), total_steps)

    step_html = templates.get_template("partials/topic_step.html").render(
        request=request,
        step=step_data,
        topic_id=topic_id,
        phase_id=phase_id,
        completed_steps=completed_steps,
        user=user,
    )
    progress_html = templates.get_template("partials/topic_progress.html").render(
        progress=progress
    )

    return HTMLResponse(step_html + progress_html)


@router.post("/steps/complete", response_class=HTMLResponse)
async def htmx_complete_step(
    request: Request,
    db: DbSession,
    user_id: UserId,
    topic_id: Annotated[str, Form()],
    step_id: Annotated[str, Form()],
    phase_id: Annotated[int, Form()],
) -> HTMLResponse:
    """Complete a step and return the updated step partial."""
    try:
        await complete_step(db, user_id, topic_id, step_id)
    except StepValidationError as e:
        span = trace.get_current_span()
        span.add_event(
            "step_complete_invalid",
            {
                "user_id": user_id,
                "topic_id": topic_id,
                "step_id": step_id,
                "error": str(e),
            },
        )
        # Step ID doesn't exist in current content (stale cached page).
        # Force a full page reload so the user gets the current steps.
        response = HTMLResponse("")
        response.headers["HX-Refresh"] = "true"
        return response
    return await _render_step_toggle(request, db, user_id, topic_id, step_id, phase_id)


@router.delete("/steps/{topic_id}/{step_id}", response_class=HTMLResponse)
async def htmx_uncomplete_step(
    request: Request,
    topic_id: str,
    step_id: str,
    db: DbSession,
    user_id: UserId,
) -> HTMLResponse:
    """Uncomplete a step and return the updated step partial."""
    try:
        await uncomplete_step(db, user_id, topic_id, step_id)
    except StepValidationError as e:
        span = trace.get_current_span()
        span.add_event(
            "step_uncomplete_invalid",
            {
                "user_id": user_id,
                "topic_id": topic_id,
                "step_id": step_id,
                "error": str(e),
            },
        )
        response = HTMLResponse("")
        response.headers["HX-Refresh"] = "true"
        return response

    phase_id = parse_phase_id_from_topic_id(topic_id) or 0

    return await _render_step_toggle(request, db, user_id, topic_id, step_id, phase_id)


@router.post("/github/submit", response_class=HTMLResponse)
@limiter.limit("10/minute")
async def htmx_submit_verification(
    request: Request,
    current_user: CurrentUser,
    requirement_id: Annotated[str, Form(max_length=100)],
    submitted_value: Annotated[str, Form(max_length=2048)] = "",
    pr_number: Annotated[str, Form(max_length=16)] = "",
) -> HTMLResponse:
    """Submit a hands-on verification and start its Durable orchestration."""
    user_id = current_user.user_id
    github_username = current_user.github_username

    requirement = get_requirement_by_id(requirement_id)

    session_maker = request.app.state.session_maker

    def _render_card(
        submission: SubmissionData | None = None,
        *,
        feedback_tasks: list | None = None,
        feedback_passed: int = 0,
        server_error: bool = False,
        server_error_message: str | None = None,
        error_banner: str | None = None,
        processing: bool = False,
    ) -> HTMLResponse:
        """Render the requirement card partial with consistent context."""
        return templates.TemplateResponse(
            request,
            "partials/requirement_card.html",
            build_requirement_card_context(
                requirement=requirement,
                github_username=github_username,
                submission=submission,
                feedback_tasks=feedback_tasks or [],
                feedback_passed=feedback_passed,
                server_error=server_error,
                server_error_message=server_error_message,
                error_banner=error_banner,
                processing=processing,
            ),
        )

    # ── Derive the canonical submission value ──────────────────────────
    if requirement is not None:
        try:
            if requirement.submission_type == SubmissionType.PR_REVIEW:
                user_input: str | None = pr_number
            elif is_derivable(requirement.submission_type):
                user_input = None
            else:
                user_input = submitted_value
                if not user_input or not user_input.strip():
                    return _render_card(
                        error_banner="Please enter a value before submitting."
                    )
            if github_username is None and not is_derivable(
                requirement.submission_type
            ):
                derived_value = user_input or ""
            else:
                derived_value = derive_submission_value(
                    requirement=requirement,
                    github_username=github_username or "",
                    user_input=user_input,
                )
        except ValueError as ve:
            return _render_card(error_banner=str(ve))
    else:
        derived_value = submitted_value

    # ── Persist job, then start Durable orchestration ──────────────────
    job_submission: VerificationJobSubmission | None = None
    try:
        job_submission = await create_verification_job(
            session_maker=session_maker,
            user_id=user_id,
            requirement_id=requirement_id,
            submitted_value=derived_value,
            github_username=github_username,
        )

        if (
            job_submission.created
            or job_submission.job.orchestration_instance_id is None
        ):
            start_result = await start_verification_orchestration(job_submission.job.id)
            async with session_maker() as write_session:
                await VerificationJobRepository(write_session).mark_starting(
                    job_submission.job.id,
                    start_result.instance_id,
                )
                await write_session.commit()

        return _render_card(processing=True)

    except _USER_FACING_ERRORS as exc:
        return _render_card(error_banner=str(exc))
    except (
        DurableVerificationConfigError,
        DurableVerificationStartError,
    ) as exc:
        span = trace.get_current_span()
        span.record_exception(exc)
        span.set_attribute("error.type", type(exc).__name__)
        logger.warning(
            "htmx.submit.durable_start_failed",
            extra={
                "user_id": user_id,
                "requirement_id": requirement_id,
                "error_type": type(exc).__name__,
            },
        )
        if job_submission is not None:
            async with session_maker() as write_session:
                await VerificationJobRepository(write_session).mark_server_error(
                    job_submission.job.id,
                    error_code="durable_start_failed",
                    error_message=_DURABLE_START_ERROR_MESSAGE,
                )
                await write_session.commit()
        return _render_card(
            server_error=True,
            server_error_message=_DURABLE_START_ERROR_MESSAGE,
        )
    except Exception as exc:
        span = trace.get_current_span()
        span.record_exception(exc)
        span.set_attribute("error.type", type(exc).__name__)
        logger.exception(
            "htmx.submit.unexpected_error",
            extra={
                "user_id": user_id,
                "requirement_id": requirement_id,
                "error_type": type(exc).__name__,
            },
        )
        return _render_card(
            server_error=True,
            server_error_message=(
                "An unexpected error occurred during verification. "
                "This attempt was not counted — please try again."
            ),
        )


@router.get("/verification/{requirement_id}/stream")
async def htmx_verification_stream(
    request: Request,
    requirement_id: str,
    current_user: CurrentUser,
) -> StreamingResponse:
    """SSE stream that pushes the DB-backed verification result when ready."""
    user_id = current_user.user_id
    stream_github_username = current_user.github_username
    session_maker = request.app.state.session_maker

    async def event_generator():
        requirement = get_requirement_by_id(requirement_id)
        if requirement is None:
            yield (
                "event: verification-result\n"
                "data: <div hx-trigger='load'"
                " hx-on::load='setTimeout(()=>location.reload(),100)'"
                "></div>\n\n"
            )
            return
        wait_timeout = get_settings().verification_wait_timeout
        deadline = asyncio.get_running_loop().time() + wait_timeout

        while True:
            try:
                state = await _load_verification_stream_state(
                    session_maker,
                    user_id,
                    requirement_id,
                )
            except Exception as exc:
                span = trace.get_current_span()
                span.record_exception(exc)
                span.set_attribute("error.type", type(exc).__name__)
                span.set_attribute("user.id", user_id)
                span.set_attribute("requirement.id", requirement_id)
                logger.exception(
                    "verification.stream.db_read_failed",
                    extra={
                        "user_id": user_id,
                        "requirement_id": requirement_id,
                        "error_type": type(exc).__name__,
                    },
                )
                yield (
                    "event: verification-result\n"
                    "data: <div class='text-red-600 text-sm p-2'>"
                    "Unable to load verification status. Refresh the page "
                    "to check for results.</div>\n\n"
                )
                return

            if state is None:
                yield (
                    "event: verification-result\n"
                    "data: <div hx-trigger='load'"
                    " hx-on::load='setTimeout(()=>location.reload(),100)'"
                    "></div>\n\n"
                )
                return

            if state.status in ACTIVE_JOB_STATUSES:
                if asyncio.get_running_loop().time() >= deadline:
                    yield (
                        "event: verification-result\n"
                        "data: <div class='text-amber-600 text-sm p-2'>"
                        "Verification is taking longer than expected. "
                        "Refresh the page to check for results.</div>\n\n"
                    )
                    return
                await asyncio.sleep(1)
                continue

            if state.status == VerificationJobStatus.SUCCEEDED:
                yield (
                    "event: verification-result\n"
                    "data: <div hx-trigger='load'"
                    " hx-on::load='setTimeout(()=>location.reload(),100)'"
                    "></div>\n\n"
                )
                return

            feedback_tasks, feedback_passed = _build_feedback_tasks_from_submission(
                state.submission
            )
            server_error = state.status == VerificationJobStatus.SERVER_ERROR
            error_banner = None
            if state.status == VerificationJobStatus.FAILED and not feedback_tasks:
                error_banner = (
                    state.submission.validation_message
                    if state.submission and state.submission.validation_message
                    else state.error_message
                )
            elif state.status == VerificationJobStatus.CANCELLED:
                error_banner = state.error_message or "Verification was cancelled."

            card_html = templates.get_template("partials/requirement_card.html").render(
                request=request,
                **build_requirement_card_context(
                    requirement=requirement,
                    github_username=stream_github_username,
                    submission=state.submission,
                    feedback_tasks=feedback_tasks,
                    feedback_passed=feedback_passed,
                    server_error=server_error,
                    server_error_message=(
                        state.error_message if server_error else None
                    ),
                    error_banner=error_banner,
                    processing=False,
                ),
            )
            data_lines = card_html.replace("\n", "\ndata: ")
            yield f"event: verification-result\ndata: {data_lines}\n\n"
            return

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",  # Disable nginx buffering
        },
    )


@router.delete("/account", response_class=HTMLResponse)
@limiter.limit("3/hour")
async def htmx_delete_account(
    request: Request,
    db: DbSession,
    user_id: UserId,
) -> HTMLResponse:
    """Delete the current user's account and redirect to home via HTMX."""
    try:
        await delete_user_account(db, user_id)
    except UserNotFoundError:
        span = trace.get_current_span()
        span.add_event("account_delete_not_found", {"user_id": user_id})
        return HTMLResponse(
            '<p class="text-sm text-red-600">Account not found.</p>',
            status_code=404,
        )

    request.session.clear()
    response = HTMLResponse("")
    response.headers["HX-Redirect"] = "/"
    return response
