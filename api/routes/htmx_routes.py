"""HTMX routes — return HTML fragments for partial page updates.

These routes handle interactive HTMX requests (step toggles, form
submissions, etc.) and return HTML partials instead of JSON.
"""

import markdown
from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse

from core.auth import UserId
from core.database import DbSession
from core.logger import get_logger
from services.steps_service import complete_step, uncomplete_step
from services.submissions_service import submit_validation

logger = get_logger(__name__)

router = APIRouter(prefix="/htmx", tags=["htmx"], include_in_schema=False)

_md = markdown.Markdown(extensions=["fenced_code", "tables"])


def _render_md(text: str | None) -> str:
    """Render markdown to HTML."""
    if not text:
        return ""
    _md.reset()
    return _md.convert(text)


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

    # Get the step data from content to re-render the partial
    from services.content_service import get_topic_by_id

    topic = get_topic_by_id(topic_id)
    step = None
    if topic:
        for s in getattr(topic, "learning_steps", []):
            if s.order == step_order:
                step = s
                break

    if step is None:
        return HTMLResponse("")

    # Get updated completed steps
    from repositories.progress_repository import StepProgressRepository

    step_repo = StepProgressRepository(db)
    progress_rows = await step_repo.get_by_user_and_topic(user_id, topic_id)
    completed_steps = {row.step_order for row in progress_rows}

    # Build step data for template
    step_data = {
        "order": step.order,
        "text": getattr(step, "text", ""),
        "action": getattr(step, "action", ""),
        "title": getattr(step, "title", ""),
        "url": getattr(step, "url", ""),
        "description": getattr(step, "description", ""),
        "description_html": _render_md(getattr(step, "description", "")),
        "code": getattr(step, "code", ""),
        "options": [],
    }
    for opt in getattr(step, "options", []):
        step_data["options"].append(
            {
                "provider": getattr(opt, "provider", ""),
                "label": getattr(opt, "label", getattr(opt, "provider", "")),
                "title": getattr(opt, "title", ""),
                "url": getattr(opt, "url", ""),
                "description_html": _render_md(getattr(opt, "description", "")),
            }
        )

    from repositories.user_repository import UserRepository

    user = await UserRepository(db).get_by_id(user_id)

    # Count total steps for progress calculation
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

    # Get step data from content
    from services.content_service import get_topic_by_id

    topic = get_topic_by_id(topic_id)

    # Extract phase_id from topic_id (e.g., "phase0-topic1" -> 0)
    phase_id = 0
    if topic_id.startswith("phase"):
        try:
            phase_id = int(topic_id.split("-")[0].replace("phase", ""))
        except (ValueError, IndexError):
            pass

    step = None
    if topic:
        for s in getattr(topic, "learning_steps", []):
            if s.order == step_order:
                step = s
                break

    if step is None:
        return HTMLResponse("")

    # Get updated completed steps
    from repositories.progress_repository import StepProgressRepository

    step_repo = StepProgressRepository(db)
    progress_rows = await step_repo.get_by_user_and_topic(user_id, topic_id)
    completed_steps = {row.step_order for row in progress_rows}

    step_data = {
        "order": step.order,
        "text": getattr(step, "text", ""),
        "action": getattr(step, "action", ""),
        "title": getattr(step, "title", ""),
        "url": getattr(step, "url", ""),
        "description": getattr(step, "description", ""),
        "description_html": _render_md(getattr(step, "description", "")),
        "code": getattr(step, "code", ""),
        "options": [],
    }
    for opt in getattr(step, "options", []):
        step_data["options"].append(
            {
                "provider": getattr(opt, "provider", ""),
                "label": getattr(opt, "label", getattr(opt, "provider", "")),
                "title": getattr(opt, "title", ""),
                "url": getattr(opt, "url", ""),
                "description_html": _render_md(getattr(opt, "description", "")),
            }
        )

    from repositories.user_repository import UserRepository

    user = await UserRepository(db).get_by_id(user_id)

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


@router.post("/github/submit", response_class=HTMLResponse)
async def htmx_submit_verification(
    request: Request,
    db: DbSession,
    user_id: UserId,
    requirement_id: str = Form(...),
    phase_id: int = Form(...),
    submission_type: str = Form(...),
    submitted_value: str = Form(...),
) -> HTMLResponse:
    """Submit a hands-on verification and return the updated requirement card."""
    from repositories.user_repository import UserRepository

    user = await UserRepository(db).get_by_id(user_id)
    github_username = user.github_username if user else None

    result = await submit_validation(
        db=db,
        user_id=user_id,
        requirement_id=requirement_id,
        submitted_value=submitted_value,
        github_username=github_username,
    )

    # Build template context for the requirement card
    from repositories.submission_repository import SubmissionRepository
    from services.hands_on_verification_service import get_requirement_by_id

    requirement = get_requirement_by_id(requirement_id)
    submission_repo = SubmissionRepository(db)
    submission = await submission_repo.get_by_user_and_requirement(
        user_id, requirement_id
    )

    # Parse feedback tasks if available
    feedback_tasks = []
    feedback_passed = 0
    if hasattr(result, "tasks") and result.tasks:
        for task in result.tasks:
            feedback_tasks.append(
                {
                    "name": getattr(task, "name", ""),
                    "passed": getattr(task, "passed", False),
                    "message": getattr(task, "message", ""),
                }
            )
            if getattr(task, "passed", False):
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
    certificate_type: str = Form("full_completion"),
    recipient_name: str = Form(""),
) -> HTMLResponse:
    """Create a certificate and return the certificate card HTML."""
    from services.certificates_service import create_certificate

    certificate = await create_certificate(
        db=db,
        user_id=user_id,
        certificate_type=certificate_type,
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
