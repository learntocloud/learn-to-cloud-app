"""Page routes — server-side rendered HTML pages.

These routes serve full Jinja2 pages. They call the same services as the
JSON API routes but render HTML templates instead of returning JSON.
"""

from datetime import UTC, datetime

import markdown
from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse

from core.auth import OptionalUserId, UserId
from core.database import DbSession
from core.logger import get_logger
from repositories.user_repository import UserRepository
from services.certificates_service import (
    get_user_certificates_with_eligibility,
    verify_certificate,
)
from services.content_service import (
    get_all_phases,
    get_phase_by_slug,
    get_topic_by_slugs,
)
from services.dashboard_service import get_dashboard
from services.progress_service import fetch_user_progress
from services.users_service import get_public_profile

logger = get_logger(__name__)

router = APIRouter(tags=["pages"], include_in_schema=False)

# Markdown renderer for step descriptions
_md = markdown.Markdown(extensions=["fenced_code", "tables"])


def _render_md(text: str | None) -> str:
    """Render markdown text to HTML. Returns empty string if input is None."""
    if not text:
        return ""
    _md.reset()
    return _md.convert(text)


async def _get_user_or_none(db, user_id: int | None):
    """Get user from DB if authenticated, else None."""
    if user_id is None:
        return None
    repo = UserRepository(db)
    return await repo.get_by_id(user_id)


def _template_context(request: Request, user=None, **kwargs) -> dict:
    """Build common template context."""
    return {
        "request": request,
        "user": user,
        "now": datetime.now(UTC),
        **kwargs,
    }


@router.get("/", response_class=HTMLResponse)
async def home_page(
    request: Request,
    db: DbSession,
    user_id: OptionalUserId,
) -> HTMLResponse:
    """Home page with phase overview."""
    user = await _get_user_or_none(db, user_id)
    phases = get_all_phases()

    return request.app.state.templates.TemplateResponse(
        "pages/home.html",
        _template_context(request, user=user, phases=phases),
    )


@router.get("/phase/{phase_id:int}", response_class=HTMLResponse)
async def phase_page(
    request: Request,
    phase_id: int,
    db: DbSession,
    user_id: OptionalUserId,
) -> HTMLResponse:
    """Single phase detail with topics and verification."""
    user = await _get_user_or_none(db, user_id)
    phase = get_phase_by_slug(f"phase{phase_id}")
    if phase is None:
        return request.app.state.templates.TemplateResponse(
            "pages/404.html",
            _template_context(request, user=user),
            status_code=404,
        )

    # Topics are already full Topic objects on the Phase
    topics = [
        {
            "name": t.name,
            "slug": t.slug,
            "is_capstone": getattr(t, "is_capstone", False),
            "progress": None,
        }
        for t in phase.topics
    ]

    # Build requirements and submissions
    requirements = []
    submissions_by_req = {}
    hands_on = getattr(phase, "hands_on_verification", None)
    if hands_on and hasattr(hands_on, "requirements"):
        requirements = hands_on.requirements

    # Fetch progress for authenticated users
    progress = None
    if user_id is not None:
        user_progress = await fetch_user_progress(db, user_id)
        phase_progress = user_progress.phases.get(phase.order)
        if phase_progress:
            pct = (
                round(
                    phase_progress.steps_completed
                    / phase_progress.steps_required
                    * 100
                )
                if phase_progress.steps_required > 0
                else 0
            )
            progress = {
                "percentage": pct,
                "steps_completed": phase_progress.steps_completed,
                "steps_required": phase_progress.steps_required,
            }

    return request.app.state.templates.TemplateResponse(
        "pages/phase.html",
        _template_context(
            request,
            user=user,
            phase=phase,
            topics=topics,
            requirements=requirements,
            submissions_by_req=submissions_by_req,
            progress=progress,
        ),
    )


@router.get("/phase/{phase_id:int}/{topic_slug}", response_class=HTMLResponse)
async def topic_page(
    request: Request,
    phase_id: int,
    topic_slug: str,
    db: DbSession,
    user_id: OptionalUserId,
) -> HTMLResponse:
    """Single topic with learning steps."""
    user = await _get_user_or_none(db, user_id)
    phase_slug = f"phase{phase_id}"
    phase = get_phase_by_slug(phase_slug)
    topic = get_topic_by_slugs(phase_slug, topic_slug)

    if phase is None or topic is None:
        return request.app.state.templates.TemplateResponse(
            "pages/404.html",
            _template_context(request, user=user),
            status_code=404,
        )

    # Get completed steps for authenticated users
    completed_steps: set[int] = set()
    if user_id is not None:
        from repositories.progress_repository import StepProgressRepository

        step_repo = StepProgressRepository(db)
        progress_rows = await step_repo.get_by_user_and_topic(user_id, topic.id)
        completed_steps = {row.step_order for row in progress_rows}

    # Pre-render markdown for step descriptions
    steps = []
    for step in getattr(topic, "learning_steps", []):
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
        steps.append(step_data)

    # Prev/next navigation — phase.topics is a list of Topic objects
    all_topics = phase.topics
    current_idx = next(
        (i for i, t in enumerate(all_topics) if t.slug == topic_slug), -1
    )
    prev_topic = None
    next_topic = None
    if current_idx > 0:
        prev_t = all_topics[current_idx - 1]
        prev_topic = {"slug": prev_t.slug, "name": prev_t.name}
    if 0 <= current_idx < len(all_topics) - 1:
        next_t = all_topics[current_idx + 1]
        next_topic = {"slug": next_t.slug, "name": next_t.name}

    # Progress calculation
    total_steps = len(steps)
    progress = None
    if user_id is not None and total_steps > 0:
        progress = {
            "completed": len(completed_steps),
            "total": total_steps,
            "percentage": round(len(completed_steps) / total_steps * 100),
        }

    return request.app.state.templates.TemplateResponse(
        "pages/topic.html",
        _template_context(
            request,
            user=user,
            topic=topic,
            steps=steps,
            phase_slug=phase_slug,
            phase_name=phase.name,
            phase_id=phase.order,
            completed_steps=completed_steps,
            prev_topic=prev_topic,
            next_topic=next_topic,
            progress=progress,
        ),
    )


@router.get("/dashboard", response_class=HTMLResponse)
async def dashboard_page(
    request: Request,
    db: DbSession,
    user_id: UserId,
) -> HTMLResponse:
    """Authenticated dashboard with progress."""
    user = await _get_user_or_none(db, user_id)
    if user is None:
        return request.app.state.templates.TemplateResponse(
            "pages/404.html",
            _template_context(request),
            status_code=404,
        )

    dashboard = await get_dashboard(
        db,
        user_id,
        user_email=user.email,
        user_first_name=user.first_name,
        user_last_name=user.last_name,
        user_avatar_url=user.avatar_url,
        user_github_username=user.github_username,
        is_admin=user.is_admin,
    )

    return request.app.state.templates.TemplateResponse(
        "pages/dashboard.html",
        _template_context(
            request,
            user=user,
            phases=dashboard.phases,
            badges=dashboard.badges,
        ),
    )


@router.get("/certificates", response_class=HTMLResponse)
async def certificates_page(
    request: Request,
    db: DbSession,
    user_id: UserId,
) -> HTMLResponse:
    """Certificate management page."""
    user = await _get_user_or_none(db, user_id)
    certificates_data = await get_user_certificates_with_eligibility(db, user_id)
    certificates = certificates_data.certificates
    eligible = certificates_data.is_eligible

    # Check if user already has a certificate
    certificate = certificates[0] if certificates else None

    return request.app.state.templates.TemplateResponse(
        "pages/certificates.html",
        _template_context(
            request,
            user=user,
            certificates=certificates,
            eligible=eligible,
            certificate=certificate,
        ),
    )


@router.get("/profile/{username}", response_class=HTMLResponse)
async def profile_page(
    request: Request,
    username: str,
    db: DbSession,
    user_id: OptionalUserId,
) -> HTMLResponse:
    """Public user profile."""
    user = await _get_user_or_none(db, user_id)
    profile = await get_public_profile(db, username, user_id)

    if profile is None:
        return request.app.state.templates.TemplateResponse(
            "pages/404.html",
            _template_context(request, user=user),
            status_code=404,
        )

    return request.app.state.templates.TemplateResponse(
        "pages/profile.html",
        _template_context(request, user=user, profile=profile),
    )


@router.get("/verify/{code}", response_class=HTMLResponse)
async def verify_page(
    request: Request,
    code: str,
    db: DbSession,
    user_id: OptionalUserId,
) -> HTMLResponse:
    """Certificate verification page."""
    user = await _get_user_or_none(db, user_id)
    certificate = await verify_certificate(db, code)

    return request.app.state.templates.TemplateResponse(
        "pages/verify.html",
        _template_context(request, user=user, certificate=certificate),
    )


@router.get("/faq", response_class=HTMLResponse)
async def faq_page(
    request: Request,
    db: DbSession,
    user_id: OptionalUserId,
) -> HTMLResponse:
    """FAQ page."""
    user = await _get_user_or_none(db, user_id)

    return request.app.state.templates.TemplateResponse(
        "pages/faq.html",
        _template_context(request, user=user),
    )
