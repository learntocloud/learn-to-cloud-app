"""HTMX routes — return HTML fragments for partial page updates.

These routes handle interactive HTMX requests (step toggles, form
submissions, etc.) and return HTML partials instead of JSON.
"""

from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse

from core.auth import UserId
from core.database import DbSession
from core.logger import get_logger
from core.ratelimit import limiter
from rendering.steps import build_step_data
from services.certificates_service import create_certificate
from services.content_service import get_topic_by_id
from services.hands_on_verification_service import get_requirement_by_id
from services.steps_service import complete_step, get_completed_steps, uncomplete_step
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

logger = get_logger(__name__)

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

    # Extract phase_id from topic_id (e.g., "phase0-topic1" -> 0)
    phase_id = 0
    if topic_id.startswith("phase"):
        try:
            phase_id = int(topic_id.split("-")[0].replace("phase", ""))
        except (ValueError, IndexError):
            pass

    return await _render_step_toggle(
        request, db, user_id, topic_id, step_order, phase_id
    )


@router.post("/github/submit", response_class=HTMLResponse)
@limiter.limit("6/hour")
async def htmx_submit_verification(
    request: Request,
    db: DbSession,
    user_id: UserId,
    requirement_id: str = Form(..., max_length=100),
    phase_id: int = Form(...),
    submission_type: str = Form(..., max_length=50),
    submitted_value: str = Form(..., max_length=2048),
) -> HTMLResponse:
    """Submit a hands-on verification and return the updated requirement card."""
    user = await get_user_by_id(db, user_id)
    github_username = user.github_username if user else None

    try:
        result = await submit_validation(
            db=db,
            user_id=user_id,
            requirement_id=requirement_id,
            submitted_value=submitted_value,
            github_username=github_username,
        )
    except RequirementNotFoundError:
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
        return HTMLResponse(
            f'<div class="text-amber-600 text-sm p-2">{e}</div>',
            status_code=429,
            headers={"Retry-After": "3600"},
        )
    except CooldownActiveError as e:
        return HTMLResponse(
            f'<div class="text-amber-600 text-sm p-2">{e}</div>',
            status_code=429,
            headers={"Retry-After": str(e.retry_after_seconds)},
        )
    except GitHubUsernameRequiredError as e:
        return HTMLResponse(
            f'<div class="text-red-600 text-sm p-2">{e}</div>',
            status_code=400,
        )
    except ConcurrentSubmissionError as e:
        return HTMLResponse(
            f'<div class="text-amber-600 text-sm p-2">{e}</div>',
            status_code=409,
        )

    requirement = get_requirement_by_id(requirement_id)

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

    return request.app.state.templates.TemplateResponse(
        "partials/requirement_card.html",
        {
            "request": request,
            "requirement": requirement,
            "submission": submission,
            "phase_id": phase_id,
            "feedback_tasks": feedback_tasks,
            "feedback_passed": feedback_passed,
        },
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

    # Return a simple card for the new certificate
    name = certificate.recipient_name
    code = certificate.verification_code
    cert_id = certificate.id
    pdf = f"/api/certificates/{cert_id}/pdf"
    png = f"/api/certificates/{cert_id}/png"
    link_cls = (
        "text-sm font-medium text-blue-600" " hover:text-blue-500 dark:text-blue-400"
    )
    html = (
        '<div class="p-6 rounded-lg border'
        ' border-gray-200 dark:border-gray-700">'
        '<div class="flex items-center justify-between mb-3">'
        '<h3 class="font-semibold text-gray-900'
        ' dark:text-white">Full Completion</h3>'
        '<span class="text-sm text-gray-500'
        ' dark:text-gray-400">Just now</span>'
        "</div>"
        '<p class="text-sm text-gray-600'
        ' dark:text-gray-400 mb-4">'
        f"Recipient: {name} &middot; Code: "
        f'<code class="bg-gray-100 dark:bg-gray-800'
        f' px-1 rounded text-xs">{code}</code>'
        "</p>"
        '<div class="flex gap-3">'
        f'<a href="{pdf}" class="{link_cls}">'
        "📄 PDF</a>"
        f'<a href="{png}" class="{link_cls}">'
        "🖼️ PNG</a>"
        "</div></div>"
    )
    return HTMLResponse(html)


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
        return HTMLResponse(
            '<p class="text-sm text-red-600">Account not found.</p>',
            status_code=404,
        )

    request.session.clear()
    response = HTMLResponse("")
    response.headers["HX-Redirect"] = "/"
    return response
