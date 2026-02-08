"""HTMX routes — return HTML fragments for partial page updates.

These routes handle interactive HTMX requests (step toggles, form
submissions, etc.) and return HTML partials instead of JSON.
"""

import json
import logging

from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse

from core.auth import UserId
from core.database import DbSession, DbSessionReadOnly
from core.ratelimit import limiter
from rendering.steps import build_step_data
from services.certificates_service import create_certificate
from services.content_service import get_topic_by_id
from services.hands_on_verification_service import get_requirement_by_id
from services.steps_service import (
    complete_step,
    get_completed_steps,
    parse_phase_id_from_topic_id,
    uncomplete_step,
)
from services.submissions_service import (
    AlreadyValidatedError,
    ConcurrentSubmissionError,
    CooldownActiveError,
    DailyLimitExceededError,
    GitHubUsernameRequiredError,
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
    step_order: int,
    phase_id: int,
) -> HTMLResponse:
    """Shared rendering for step complete/uncomplete HTMX responses.

    Looks up the step content, fetches updated progress, and returns
    the combined step + progress HTML partials.
    """
    topic = get_topic_by_id(topic_id)
    step = None
    if topic:
        for s in getattr(topic, "learning_steps", []):
            if s.order == step_order:
                step = s
                break

    if step is None:
        logger.warning(
            "htmx.step_toggle.step_not_found",
            extra={"user_id": user_id, "topic_id": topic_id, "step_order": step_order},
        )
        return HTMLResponse("")

    completed_steps = await get_completed_steps(db, user_id, topic_id)
    step_data = build_step_data(step)
    user = await get_user_by_id(db, user_id)

    total_steps = len(getattr(topic, "learning_steps", []))
    progress = {
        "completed": len(completed_steps),
        "total": total_steps,
        "percentage": round(len(completed_steps) / total_steps * 100)
        if total_steps > 0
        else 0,
    }

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
async def htmx_complete_step(
    request: Request,
    db: DbSession,
    user_id: UserId,
    topic_id: str = Form(...),
    step_order: int = Form(...),
    phase_id: int = Form(...),
) -> HTMLResponse:
    """Complete a step and return the updated step partial."""
    await complete_step(db, user_id, topic_id, step_order)
    return await _render_step_toggle(
        request, db, user_id, topic_id, step_order, phase_id
    )


@router.delete("/steps/{topic_id}/{step_order}", response_class=HTMLResponse)
async def htmx_uncomplete_step(
    request: Request,
    topic_id: str,
    step_order: int,
    db: DbSession,
    user_id: UserId,
) -> HTMLResponse:
    """Uncomplete a step and return the updated step partial."""
    await uncomplete_step(db, user_id, topic_id, step_order)

    phase_id = parse_phase_id_from_topic_id(topic_id) or 0

    return await _render_step_toggle(
        request, db, user_id, topic_id, step_order, phase_id
    )


@router.post("/github/submit", response_class=HTMLResponse)
async def htmx_submit_verification(
    request: Request,
    db: DbSessionReadOnly,
    user_id: UserId,
    requirement_id: str = Form(..., max_length=100),
    phase_id: int = Form(...),
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
        submission: object | None = None,
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
                "phase_id": phase_id,
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

        # Restore previous feedback tasks from stored JSON
        feedback_tasks = []
        feedback_passed = 0
        if existing and existing.feedback_json:
            for task_data in json.loads(existing.feedback_json):
                feedback_tasks.append(
                    {
                        "name": task_data.get("task_name", ""),
                        "passed": task_data.get("passed", False),
                        "message": task_data.get("feedback", ""),
                    }
                )
                if task_data.get("passed"):
                    feedback_passed += 1

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
    except ConcurrentSubmissionError as e:
        return _render_card(
            error_banner=str(e),
        )

    # submit_validation returns SubmissionResult which already contains the
    # upserted submission — no need to re-fetch from the repository.
    submission = result.submission

    # Parse feedback tasks if available
    feedback_tasks = []
    feedback_passed = 0
    if result.task_results:
        for task in result.task_results:
            feedback_tasks.append(
                {
                    "name": task.task_name,
                    "passed": task.passed,
                    "message": task.feedback,
                }
            )
            if task.passed:
                feedback_passed += 1

    # Detect server-side errors so the template can tell the user
    # this attempt was not counted against their cooldown/quota.
    is_server_error = (
        not result.is_valid and submission and not submission.verification_completed
    )

    return _render_card(
        submission=submission,
        feedback_tasks=feedback_tasks,
        feedback_passed=feedback_passed,
        server_error=is_server_error,
        server_error_message=result.message if is_server_error else None,
    )


@router.post("/certificates", response_class=HTMLResponse)
async def htmx_create_certificate(
    request: Request,
    db: DbSession,
    user_id: UserId,
    recipient_name: str = Form(""),
) -> HTMLResponse:
    """Create a certificate and return the certificate card HTML."""
    certificate = await create_certificate(
        db=db,
        user_id=user_id,
        recipient_name=recipient_name,
    )

    # Return the certificate card partial
    return request.app.state.templates.TemplateResponse(
        "partials/certificate_card.html",
        {
            "request": request,
            "certificate": certificate,
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
        await db.commit()
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
