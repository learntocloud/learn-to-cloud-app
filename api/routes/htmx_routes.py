"""HTMX routes — return HTML fragments for partial page updates.

These routes handle interactive HTMX requests (step toggles, form
submissions, etc.) and return HTML partials instead of JSON.
"""

import logging

from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse

from core.auth import UserId
from core.database import DbSession, DbSessionReadOnly
from core.ratelimit import limiter
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
    submit_validation,
)
from services.users_service import (
    UserNotFoundError,
    delete_user_account,
    get_user_by_id,
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

    step_html = request.app.state.templates.get_template(
        "partials/topic_step.html"
    ).render(
        request=request,
        step=step_data,
        topic_id=topic_id,
        phase_id=phase_id,
        completed_steps=completed_steps,
        user=user,
    )
    progress_html = request.app.state.templates.get_template(
        "partials/topic_progress.html"
    ).render(progress=progress)

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
    db: DbSessionReadOnly,  # Read-only: write sessions created via session_maker below
    user_id: UserId,
    requirement_id: str = Form(..., max_length=100),
    submitted_value: str = Form(..., max_length=2048),
) -> HTMLResponse:
    """Submit a hands-on verification and return the updated requirement card."""
    user = await get_user_by_id(db, user_id)
    github_username = user.github_username if user else None

    requirement = get_requirement_by_id(requirement_id)

    # session_maker lets submit_validation open short-lived sessions
    # instead of holding the route's DbSession during long LLM calls.
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
    ) -> HTMLResponse:
        """Render the requirement card partial with consistent context."""
        return request.app.state.templates.TemplateResponse(
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
            },
        )

    try:
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

    # submit_validation returns SubmissionResult which already contains the
    # upserted submission — no need to re-fetch from the repository.
    submission = result.submission

    feedback_tasks, feedback_passed = build_feedback_tasks_from_results(
        result.task_results
    )

    # Show the validation message as an error banner when the submission
    # failed but there are no per-task feedback details (e.g. deployed API).
    error_banner = None
    if not result.is_valid and not result.is_server_error and not feedback_tasks:
        error_banner = result.message

    response = _render_card(
        submission=submission,
        feedback_tasks=feedback_tasks,
        feedback_passed=feedback_passed,
        server_error=result.is_server_error,
        server_error_message=result.message if result.is_server_error else None,
        error_banner=error_banner,
    )

    # On successful verification, refresh the page so the stepper UI
    # reveals the next requirement card.
    if result.is_valid:
        response.headers["HX-Refresh"] = "true"

    return response


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
