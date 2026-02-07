"""Page routes — server-side rendered HTML pages.

These routes serve full Jinja2 pages. They call the same services as the
JSON API routes but render HTML templates instead of returning JSON.
"""

from datetime import UTC, datetime

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse

from core.auth import OptionalUserId, UserId
from core.database import DbSession
from core.logger import get_logger
from models import User
from rendering.steps import build_step_data
from services.certificates_service import (
    get_user_certificates_with_eligibility,
    verify_certificate,
)
from services.content_service import (
    get_all_phases,
    get_phase_by_slug,
    get_topic_by_slugs,
)
from services.dashboard_service import get_phases_list
from services.progress_service import get_phase_detail_progress
from services.steps_service import get_completed_steps
from services.users_service import get_public_profile, get_user_by_id

logger = get_logger(__name__)

router = APIRouter(tags=["pages"], include_in_schema=False)


async def _get_user_or_none(db: DbSession, user_id: int | None) -> User | None:
    """Get user from DB if authenticated, else None."""
    if user_id is None:
        return None
    return await get_user_by_id(db, user_id)


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

    # Single service call for all progress (per-topic + phase-level)
    progress = None
    if user_id is not None:
        detail = await get_phase_detail_progress(db, user_id, phase)
        for i, t in enumerate(phase.topics):
            tp = detail.topic_progress.get(t.id)
            if tp:
                topics[i]["progress"] = {
                    "completed": tp.steps_completed,
                    "total": tp.steps_total,
                }
        progress = {
            "percentage": detail.percentage,
            "steps_completed": detail.steps_completed,
            "steps_required": detail.steps_total,
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
        completed_steps = await get_completed_steps(db, user_id, topic.id)

    # Pre-render markdown for step descriptions
    steps = [build_step_data(step) for step in getattr(topic, "learning_steps", [])]

    # Prev/next navigation — phase.topics is a list of Topic objects
    all_topics = phase.topics
    current_idx = next(
        (i for i, t in enumerate(all_topics) if t.slug == topic_slug), -1
    )
    phase_link = {"slug": None, "name": phase.name, "url": f"/phase/{phase_id}"}
    prev_topic = None
    next_topic = None
    if current_idx == 0:
        prev_topic = phase_link
    elif current_idx > 0:
        prev_t = all_topics[current_idx - 1]
        prev_topic = {
            "slug": prev_t.slug,
            "name": prev_t.name,
            "url": f"/phase/{phase_id}/{prev_t.slug}",
        }
    if current_idx == len(all_topics) - 1:
        next_topic = phase_link
    elif 0 <= current_idx < len(all_topics) - 1:
        next_t = all_topics[current_idx + 1]
        next_topic = {
            "slug": next_t.slug,
            "name": next_t.name,
            "url": f"/phase/{phase_id}/{next_t.slug}",
        }

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

    dashboard = await get_phases_list(db, user_id)

    return request.app.state.templates.TemplateResponse(
        "pages/dashboard.html",
        _template_context(
            request,
            user=user,
            phases=dashboard,
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
    certificates, eligible = await get_user_certificates_with_eligibility(db, user_id)

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
