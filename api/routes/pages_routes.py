"""Page routes — server-side rendered HTML pages.

These routes serve full Jinja2 pages. They call the same services as the
JSON API routes but render HTML templates instead of returning JSON.
"""

import logging
from datetime import UTC, datetime

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse

from core.auth import OptionalUserId, UserId
from core.database import DbSession
from core.templates import templates
from models import User
from rendering.context import (
    FAQS,
    HELP_LINKS,
    build_phase_topics,
    build_progress_dict,
    build_topic_nav,
)
from rendering.steps import build_step_data
from services.content_service import (
    get_all_phases,
    get_phase_by_slug,
    get_topic_by_slugs,
)
from services.dashboard_service import get_dashboard_data
from services.phase_requirements_service import (
    is_phase_verification_locked,
)
from services.progress_service import get_phase_detail_progress
from services.steps_service import get_valid_completed_steps
from services.submissions_service import get_phase_submission_context
from services.users_service import get_user_by_id

logger = logging.getLogger(__name__)

router = APIRouter(tags=["pages"], include_in_schema=False)


async def _get_user_or_none(db: DbSession, user_id: int | None) -> User | None:
    """Get user from DB if authenticated, else None."""
    if user_id is None:
        return None
    return await get_user_by_id(db, user_id)


def _template_context(
    request: Request, user: User | None = None, **kwargs: object
) -> dict:
    """Build common template context."""
    return {
        "request": request,
        "user": user,
        "now": datetime.now(UTC),
        **kwargs,
    }


@router.get("/", response_class=HTMLResponse, summary="Home page")
async def home_page(
    request: Request,
    db: DbSession,
    user_id: OptionalUserId,
) -> HTMLResponse:
    """Home page with phase overview."""
    user = await _get_user_or_none(db, user_id)
    phases = get_all_phases()

    return templates.TemplateResponse(
        "pages/home.html",
        _template_context(request, user=user, phases=phases),
    )


@router.get("/curriculum", response_class=HTMLResponse, summary="Curriculum overview")
async def curriculum_page(
    request: Request,
    db: DbSession,
    user_id: OptionalUserId,
) -> HTMLResponse:
    """Full curriculum overview with all phases and topics."""
    user = await _get_user_or_none(db, user_id)
    phases = get_all_phases()

    return templates.TemplateResponse(
        "pages/curriculum.html",
        _template_context(request, user=user, phases=phases),
    )


@router.get(
    "/phase/{phase_id:int}",
    response_class=HTMLResponse,
    summary="Phase detail",
)
async def phase_page(
    request: Request,
    phase_id: int,
    db: DbSession,
    user_id: UserId,
) -> HTMLResponse:
    """Single phase detail with topics and verification (requires auth)."""
    user = await _get_user_or_none(db, user_id)
    phase = get_phase_by_slug(f"phase{phase_id}")
    if phase is None:
        return templates.TemplateResponse(
            "pages/404.html",
            _template_context(request, user=user),
            status_code=404,
        )

    detail = await get_phase_detail_progress(db, user_id, phase)
    topics, progress = build_phase_topics(phase, detail)

    requirements = []
    hands_on = phase.hands_on_verification
    if hands_on:
        requirements = hands_on.requirements

    sub_context = await get_phase_submission_context(db, user_id, phase_id)
    submissions_by_req = sub_context.submissions_by_req
    feedback_by_req = sub_context.feedback_by_req

    # Sequential phase gating — check if prerequisite phase is complete
    verification_locked, prerequisite_phase_id = await is_phase_verification_locked(
        db, user_id, phase_id
    )

    return templates.TemplateResponse(
        "pages/phase.html",
        _template_context(
            request,
            user=user,
            phase=phase,
            topics=topics,
            requirements=requirements,
            submissions_by_req=submissions_by_req,
            feedback_by_req=feedback_by_req,
            progress=progress,
            verification_locked=verification_locked,
            prerequisite_phase_id=prerequisite_phase_id,
        ),
    )


@router.get(
    "/phase/{phase_id:int}/{topic_slug}",
    response_class=HTMLResponse,
    summary="Topic detail",
)
async def topic_page(
    request: Request,
    phase_id: int,
    topic_slug: str,
    db: DbSession,
    user_id: UserId,
) -> HTMLResponse:
    """Single topic with learning steps (requires auth)."""
    user = await _get_user_or_none(db, user_id)
    phase_slug = f"phase{phase_id}"
    phase = get_phase_by_slug(phase_slug)
    topic = get_topic_by_slugs(phase_slug, topic_slug)

    if phase is None or topic is None:
        return templates.TemplateResponse(
            "pages/404.html",
            _template_context(request, user=user),
            status_code=404,
        )

    completed_step_ids = await get_valid_completed_steps(db, user_id, topic)

    steps = [build_step_data(step) for step in topic.learning_steps]

    all_topics = phase.topics
    prev_topic, next_topic = build_topic_nav(
        all_topics, topic_slug, phase_id, phase.name
    )

    total_steps = len(steps)
    progress = (
        build_progress_dict(len(completed_step_ids), total_steps)
        if total_steps > 0
        else None
    )

    return templates.TemplateResponse(
        "pages/topic.html",
        _template_context(
            request,
            user=user,
            topic=topic,
            steps=steps,
            phase_slug=phase_slug,
            phase_name=phase.name,
            phase_id=phase.order,
            completed_steps=completed_step_ids,
            prev_topic=prev_topic,
            next_topic=next_topic,
            progress=progress,
        ),
    )


@router.get("/dashboard", response_class=HTMLResponse, summary="User dashboard")
async def dashboard_page(
    request: Request,
    db: DbSession,
    user_id: UserId,
) -> HTMLResponse:
    """Authenticated dashboard with progress."""
    user = await _get_user_or_none(db, user_id)
    if user is None:
        return templates.TemplateResponse(
            "pages/404.html",
            _template_context(request),
            status_code=404,
        )

    dashboard = await get_dashboard_data(db, user_id)

    return templates.TemplateResponse(
        "pages/dashboard.html",
        _template_context(
            request,
            user=user,
            dashboard=dashboard,
            help_links=HELP_LINKS,
        ),
    )


@router.get("/account", response_class=HTMLResponse, summary="Account settings")
async def account_page(
    request: Request,
    db: DbSession,
    user_id: UserId,
) -> HTMLResponse:
    """Account settings page."""
    user = await _get_user_or_none(db, user_id)
    if user is None:
        return templates.TemplateResponse(
            "pages/404.html",
            _template_context(request),
            status_code=404,
        )

    return templates.TemplateResponse(
        "pages/account.html",
        _template_context(request, user=user),
    )


@router.get("/faq", response_class=HTMLResponse, summary="FAQ")
async def faq_page(
    request: Request,
    db: DbSession,
    user_id: OptionalUserId,
) -> HTMLResponse:
    """FAQ page."""
    user = await _get_user_or_none(db, user_id)

    return templates.TemplateResponse(
        "pages/faq.html",
        _template_context(request, user=user, faqs=FAQS),
    )


@router.get("/privacy", response_class=HTMLResponse, summary="Privacy policy")
async def privacy_page(
    request: Request,
    db: DbSession,
    user_id: OptionalUserId,
) -> HTMLResponse:
    """Privacy policy page."""
    user = await _get_user_or_none(db, user_id)

    return templates.TemplateResponse(
        "pages/privacy.html",
        _template_context(request, user=user),
    )


@router.get("/terms", response_class=HTMLResponse, summary="Terms of service")
async def terms_page(
    request: Request,
    db: DbSession,
    user_id: OptionalUserId,
) -> HTMLResponse:
    """Terms of service page."""
    user = await _get_user_or_none(db, user_id)

    return templates.TemplateResponse(
        "pages/terms.html",
        _template_context(request, user=user),
    )
