"""HTMX routes — return HTML fragments for partial page updates.

These routes handle interactive HTMX requests (step toggles, form
submissions, etc.) and return HTML partials instead of JSON.

LLM-based verifications (CODE_ANALYSIS, DEVOPS_ANALYSIS) use a
background task + SSE pattern:
1. POST /htmx/github/submit — pre-validates and returns a spinner card
   immediately (~100ms)
2. Background task runs the LLM call (30-120s) and publishes the result
3. GET /htmx/verification/{requirement_id}/stream — SSE endpoint that
   pushes the result HTML when the background task finishes
"""

import asyncio
import logging

from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse
from starlette.responses import StreamingResponse

from core.auth import UserId
from core.database import DbSession, DbSessionReadOnly
from core.ratelimit import limiter
from core.templates import templates
from rendering.context import (
    build_feedback_tasks,
    build_feedback_tasks_from_results,
    build_progress_dict,
)
from rendering.steps import build_step_data
from schemas import SubmissionData
from services.content_service import get_topic_by_id
from services.hands_on_verification_service import get_requirement_by_id
from services.steps_service import (
    StepValidationError,
    complete_step,
    get_valid_completed_steps,
    parse_phase_id_from_topic_id,
    uncomplete_step,
)
from services.submissions_service import (
    AlreadyValidatedError,
    ConcurrentSubmissionError,
    CooldownActiveError,
    DailyLimitExceededError,
    GitHubUsernameRequiredError,
    PriorPhaseNotCompleteError,
    RequirementNotFoundError,
    _get_submission_lock,
    _is_llm_submission,
    pre_validate_submission,
    submit_validation,
)
from services.users_service import (
    UserNotFoundError,
    delete_user_account,
    get_user_by_id,
)
from services.verification_events import (
    complete_pending,
    create_pending,
    get_pending,
    remove_pending,
)

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
    topic_id: str = Form(...),
    step_id: str = Form(...),
    phase_id: int = Form(...),
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
    requirement_id: str = Form(..., max_length=100),
    submitted_value: str = Form(..., max_length=2048),
) -> HTMLResponse:
    """Submit a hands-on verification.

    For instant verifications (CTF tokens, profile checks, etc.): runs
    synchronously and returns the result card immediately.

    For LLM verifications (CODE_ANALYSIS, DEVOPS_ANALYSIS): kicks off a
    background task and returns a spinner card that connects to an SSE
    stream for the result.  The user sees "Analyzing..." immediately
    instead of waiting 30-120s.
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
        cooldown_seconds: int | None = None,
        cooldown_message: str | None = None,
        error_banner: str | None = None,
        processing: bool = False,
    ) -> HTMLResponse:
        """Render the requirement card partial with consistent context."""
        return templates.TemplateResponse(
            "partials/requirement_card.html",
            {
                "request": request,
                "requirement": requirement,
                "submission": submission,
                "feedback_tasks": feedback_tasks or [],
                "feedback_passed": feedback_passed,
                "server_error": server_error,
                "server_error_message": server_error_message,
                "cooldown_seconds": cooldown_seconds,
                "cooldown_message": cooldown_message,
                "error_banner": error_banner,
                "processing": processing,
            },
        )

    # ── Pre-validation (same for sync and async paths) ──────────────────
    # These checks are fast (<100ms) and raise on failure.  If any raise,
    # the user gets immediate feedback before any background task starts.
    try:
        # Dry-run the pre-validation checks from submit_validation by
        # attempting a synchronous call.  For non-LLM submissions this
        # runs the full verification.  For LLM submissions we'll catch
        # the result below and decide whether to go async.
        is_llm = requirement is not None and _is_llm_submission(
            requirement.submission_type
        )

        if is_llm:
            # For LLM submissions: run ONLY pre-validation, then go async.
            await pre_validate_submission(
                session_maker=session_maker,
                user_id=user_id,
                requirement_id=requirement_id,
                submitted_value=submitted_value,
                github_username=github_username,
            )

            # Check concurrent lock
            submission_lock = await _get_submission_lock(user_id, requirement_id)
            if submission_lock.locked():
                raise ConcurrentSubmissionError(
                    "A verification is already in progress. "
                    "Please wait for it to complete."
                )

            # Register pending event + fire background task
            create_pending(user_id, requirement_id)

            asyncio.create_task(
                _run_verification_background(
                    session_maker=session_maker,
                    user_id=user_id,
                    requirement_id=requirement_id,
                    submitted_value=submitted_value,
                    github_username=github_username,
                )
            )

            # Return the processing card with SSE connection
            return _render_card(processing=True)

        # Non-LLM: run synchronously (instant verifications <1s)
        result = await submit_validation(
            session_maker=session_maker,
            user_id=user_id,
            requirement_id=requirement_id,
            submitted_value=submitted_value,
            github_username=github_username,
        )
    except RequirementNotFoundError:
        logger.warning(
            "htmx.submit.requirement_not_found",
            extra={"user_id": user_id, "requirement_id": requirement_id},
        )
        return HTMLResponse(
            '<div class="text-red-600 text-sm p-2">Requirement not found.</div>',
            status_code=404,
        )
    except AlreadyValidatedError:
        return HTMLResponse(
            '<div class="text-green-600 text-sm p-2">'
            "You have already completed this requirement.</div>",
            status_code=200,
        )
    except DailyLimitExceededError as e:
        return _render_card(
            submission=e.existing_submission,
            error_banner=str(e),
        )
    except CooldownActiveError as e:
        existing = e.existing_submission

        feedback_tasks, feedback_passed = build_feedback_tasks(
            existing.feedback_json if existing else None
        )

        return _render_card(
            submission=existing,
            feedback_tasks=feedback_tasks,
            feedback_passed=feedback_passed,
            cooldown_seconds=e.retry_after_seconds,
            cooldown_message=str(e),
        )
    except GitHubUsernameRequiredError:
        return _render_card(
            error_banner="You need to link your GitHub account to submit. "
            "Please sign out and sign in with GitHub.",
        )
    except PriorPhaseNotCompleteError as e:
        return _render_card(
            error_banner=str(e),
        )
    except ConcurrentSubmissionError as e:
        return _render_card(
            error_banner=str(e),
        )
    except Exception:
        logger.exception(
            "htmx.submit.unexpected_error",
            extra={"user_id": user_id, "requirement_id": requirement_id},
        )
        return _render_card(
            server_error=True,
            server_error_message=(
                "An unexpected error occurred during verification. "
                "This attempt was not counted — please try again."
            ),
        )

    # ── Synchronous result (non-LLM submissions) ───────────────────────
    return _render_result_card(request, requirement, result)


def _render_result_card(
    request: Request,
    requirement: object,
    result: "SubmissionResult",
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
        "partials/requirement_card.html",
        {
            "request": request,
            "requirement": requirement,
            "submission": submission,
            "feedback_tasks": feedback_tasks or [],
            "feedback_passed": feedback_passed,
            "server_error": result.is_server_error,
            "server_error_message": result.message if result.is_server_error else None,
            "cooldown_seconds": None,
            "cooldown_message": None,
            "error_banner": error_banner,
            "processing": False,
        },
    )

    if result.is_valid:
        response.headers["HX-Refresh"] = "true"

    return response


async def _run_verification_background(
    session_maker: object,
    user_id: int,
    requirement_id: str,
    submitted_value: str,
    github_username: str | None,
) -> None:
    """Background task: run LLM verification and publish result via event bus."""
    try:
        result = await submit_validation(
            session_maker=session_maker,
            user_id=user_id,
            requirement_id=requirement_id,
            submitted_value=submitted_value,
            github_username=github_username,
        )
        complete_pending(user_id, requirement_id, result=result)
    except Exception as exc:
        logger.exception(
            "verification.background.failed",
            extra={"user_id": user_id, "requirement_id": requirement_id},
        )
        complete_pending(user_id, requirement_id, error=exc)


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
    pending = get_pending(user_id, requirement_id)

    async def event_generator():
        if pending is None:
            # No pending verification — might have already completed.
            # Send an HX-Refresh to reload the page with DB state.
            yield "event: verification-result\ndata: <div hx-trigger='load' hx-get='/' hx-swap='none'></div>\n\n"
            return

        try:
            # Wait up to 3 minutes for the result
            await asyncio.wait_for(pending.event.wait(), timeout=180)
        except TimeoutError:
            yield (
                "event: verification-result\n"
                "data: <div class='text-amber-600 text-sm p-2'>"
                "Verification is taking longer than expected. "
                "Refresh the page to check for results.</div>\n\n"
            )
            return
        finally:
            # Always clean up, even on timeout or client disconnect
            remove_pending(user_id, requirement_id)

        if pending.error is not None:
            yield (
                "event: verification-result\n"
                "data: <div class='text-red-600 text-sm p-2'>"
                "An unexpected error occurred during verification. "
                "This attempt was not counted — please try again.</div>\n\n"
            )
        elif pending.result is not None:
            requirement = get_requirement_by_id(requirement_id)

            if pending.result.is_valid:
                # On success, trigger full page refresh so the stepper
                # advances to the next requirement.
                yield "event: verification-result\ndata: <div hx-trigger='load' hx-on::load='setTimeout(()=>location.reload(),100)'></div>\n\n"
            else:
                # Render the result card HTML inline
                result = pending.result
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
                    requirement=requirement,
                    submission=submission,
                    feedback_tasks=feedback_tasks or [],
                    feedback_passed=feedback_passed,
                    server_error=result.is_server_error,
                    server_error_message=(
                        result.message if result.is_server_error else None
                    ),
                    cooldown_seconds=None,
                    cooldown_message=None,
                    error_banner=error_banner,
                    processing=False,
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
