"""HTMX routes — return HTML fragments for partial page updates.

These routes handle interactive HTMX requests (step toggles, form
submissions, etc.) and return HTML partials instead of JSON.

LLM-based verifications (DEVOPS_ANALYSIS, PR_REVIEW with grading_criteria)
use a background task + SSE pattern:
1. POST /htmx/github/submit — pre-validates and returns a spinner card
   immediately (~100ms)
2. Background task runs the LLM call (30-120s) and publishes the result
3. GET /htmx/verification/{requirement_id}/stream — SSE endpoint that
   pushes the result HTML when the background task finishes
"""

import asyncio
import logging
from typing import Annotated

from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from starlette.responses import StreamingResponse

from core.auth import UserId
from core.database import DbSession, DbSessionReadOnly
from core.ratelimit import limiter
from core.templates import templates
from models import SubmissionType
from rendering.context import (
    build_feedback_tasks_from_results,
    build_progress_dict,
    build_requirement_card_context,
)
from rendering.steps import build_step_data
from schemas import SubmissionData, SubmissionResult
from services.content_service import get_topic_by_id
from services.steps_service import (
    StepValidationError,
    complete_step,
    get_valid_completed_steps,
    parse_phase_id_from_topic_id,
    uncomplete_step,
)
from services.submissions_service import (
    submit_validation,
)
from services.users_service import (
    UserNotFoundError,
    delete_user_account,
    get_user_by_id,
)
from services.verification.events import (
    get_task,
    remove_task,
    store_task,
)
from services.verification.requirements import get_requirement_by_id
from services.verification.url_derivation import derive_submission_value, is_derivable

logger = logging.getLogger(__name__)

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
        logger.warning(
            "htmx.step_toggle.step_not_found",
            extra={"user_id": user_id, "topic_id": topic_id, "step_id": step_id},
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
@limiter.limit("30/minute")
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
        logger.warning(
            "htmx.step_complete.invalid",
            extra={
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
@limiter.limit("30/minute")
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
        logger.warning(
            "htmx.step_uncomplete.invalid",
            extra={
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
    db: DbSessionReadOnly,
    user_id: UserId,
    requirement_id: Annotated[str, Form(max_length=100)],
    submitted_value: Annotated[str, Form(max_length=2048)] = "",
    pr_number: Annotated[str, Form(max_length=16)] = "",
) -> HTMLResponse:
    """Submit a hands-on verification.

    Derives the canonical URL, fires a background task, and returns a
    spinner card that connects to an SSE stream for the result.
    All validation (preconditions, LLM grading, persistence) happens
    in the background task — errors surface via SSE.
    """
    user = await get_user_by_id(db, user_id)
    github_username = user.github_username if user else None

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

    # ── Fire background task ───────────────────────────────────────────
    try:
        task = asyncio.create_task(
            submit_validation(
                session_maker=session_maker,
                user_id=user_id,
                requirement_id=requirement_id,
                submitted_value=derived_value,
                github_username=github_username,
            )
        )
        store_task(user_id, requirement_id, task)

        return _render_card(processing=True)

    except Exception as exc:
        logger.exception(
            "htmx.submit.unexpected_error",
            extra={
                "user_id": user_id,
                "requirement_id": requirement_id,
                "exc_type": type(exc).__name__,
                "exc_message": str(exc),
            },
        )
        return _render_card(
            server_error=True,
            server_error_message=(
                "An unexpected error occurred during verification. "
                "This attempt was not counted — please try again."
            ),
        )


def _render_result_card(
    request: Request,
    requirement: object,
    result: "SubmissionResult",
    github_username: str | None,
) -> HTMLResponse:
    """Render a completed verification result card."""
    submission = result.submission

    feedback_tasks, feedback_passed = build_feedback_tasks_from_results(
        result.task_results
    )

    error_banner = None
    if not result.is_valid and not result.is_server_error and not feedback_tasks:
        error_banner = result.message

    response = templates.TemplateResponse(
        request,
        "partials/requirement_card.html",
        build_requirement_card_context(
            requirement=requirement,
            github_username=github_username,
            submission=submission,
            feedback_tasks=feedback_tasks or [],
            feedback_passed=feedback_passed,
            server_error=result.is_server_error,
            server_error_message=result.message if result.is_server_error else None,
            error_banner=error_banner,
            processing=False,
        ),
    )

    if result.is_valid:
        response.headers["HX-Refresh"] = "true"

    return response


@router.get("/verification/{requirement_id}/stream")
async def htmx_verification_stream(
    request: Request,
    requirement_id: str,
    user_id: UserId,
) -> StreamingResponse:
    """SSE stream that pushes the verification result when ready.

    The HTMX SSE extension connects here after a submission is kicked off.
    When the background task completes, this endpoint sends a single SSE
    event containing the rendered result card HTML, then closes.

    If the client disconnects before the result arrives (tab close, nav),
    the result is still persisted in the DB and will show on next page load.
    """
    task = get_task(user_id, requirement_id)

    # Fetch github_username with a short-lived session so we don't hold a
    # DB connection open for the entire SSE stream (up to 180s).
    session_maker: async_sessionmaker[AsyncSession] = request.app.state.session_maker
    async with session_maker() as db:
        stream_user = await get_user_by_id(db, user_id)
        stream_github_username = stream_user.github_username if stream_user else None

    async def event_generator():
        if task is None:
            # No pending verification — might have already completed.
            # Send an HX-Refresh to reload the page with DB state.
            yield (
                "event: verification-result\n"
                "data: <div hx-trigger='load' hx-get='/'"
                " hx-swap='none'></div>\n\n"
            )
            return

        try:
            # Wait up to 3 minutes for the result
            result = await asyncio.wait_for(asyncio.shield(task), timeout=180)
        except TimeoutError:
            yield (
                "event: verification-result\n"
                "data: <div class='text-amber-600 text-sm p-2'>"
                "Verification is taking longer than expected. "
                "Refresh the page to check for results.</div>\n\n"
            )
            return
        except Exception:
            logger.exception(
                "verification.stream.task_failed",
                extra={"user_id": user_id, "requirement_id": requirement_id},
            )
            yield (
                "event: verification-result\n"
                "data: <div class='text-red-600 text-sm p-2'>"
                "An unexpected error occurred during verification. "
                "This attempt was not counted — please try again.</div>\n\n"
            )
            return
        finally:
            # Always clean up, even on timeout or client disconnect
            remove_task(user_id, requirement_id)

        requirement = get_requirement_by_id(requirement_id)

        if result.is_valid:
            # On success, trigger full page refresh so the stepper
            # advances to the next requirement.
            yield (
                "event: verification-result\n"
                "data: <div hx-trigger='load'"
                " hx-on::load='setTimeout(()=>location.reload(),100)'"
                "></div>\n\n"
            )
        else:
            # Render the result card HTML inline
            submission = result.submission

            feedback_tasks, feedback_passed = build_feedback_tasks_from_results(
                result.task_results
            )
            error_banner = None
            if (
                not result.is_valid
                and not result.is_server_error
                and not feedback_tasks
            ):
                error_banner = result.message

            html = templates.get_template("partials/requirement_card.html").render(
                request=request,
                **build_requirement_card_context(
                    requirement=requirement,
                    github_username=stream_github_username,
                    submission=submission,
                    feedback_tasks=feedback_tasks or [],
                    feedback_passed=feedback_passed,
                    server_error=result.is_server_error,
                    server_error_message=(
                        result.message if result.is_server_error else None
                    ),
                    error_banner=error_banner,
                    processing=False,
                ),
            )
            # SSE data lines: replace newlines with \ndata: for multi-line HTML
            data_lines = html.replace("\n", "\ndata: ")
            yield f"event: verification-result\ndata: {data_lines}\n\n"

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
        logger.warning(
            "htmx.account_delete.not_found",
            extra={"user_id": user_id},
        )
        return HTMLResponse(
            '<p class="text-sm text-red-600">Account not found.</p>',
            status_code=404,
        )

    request.session.clear()
    response = HTMLResponse("")
    response.headers["HX-Redirect"] = "/"
    return response
