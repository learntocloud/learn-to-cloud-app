"""Page routes — server-side rendered HTML pages.

These routes serve full Jinja2 pages. They call the same services as the
JSON API routes but render HTML templates instead of returning JSON.
"""

import logging
from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Query, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from learn_to_cloud_shared.content_service import (
    get_curriculum_overview,
    get_phase_by_slug,
)
from learn_to_cloud_shared.core.database import DbSession
from learn_to_cloud_shared.models import User

from learn_to_cloud.core.auth import (
    CurrentAccount,
    OptionalCurrentAccount,
)
from learn_to_cloud.core.routing import LoginRedirectRoute
from learn_to_cloud.core.templates import templates
from learn_to_cloud.rendering.page_content import (
    COMMUNITY_LINKS,
    FAQS,
    HELP_LINKS,
)
from learn_to_cloud.rendering.progress import (
    build_phase_topics,
    build_progress_dict,
)
from learn_to_cloud.rendering.topic_navigation import build_topic_nav
from learn_to_cloud.services.community_service import get_community_page_data
from learn_to_cloud.services.dashboard_service import get_dashboard_data
from learn_to_cloud.services.progress_service import fetch_phase_progress
from learn_to_cloud.services.steps_service import get_valid_completed_steps
from learn_to_cloud.services.verification_page_service import (
    get_phase_verification_workspace,
    get_verifications_overview,
)

logger = logging.getLogger(__name__)

router = APIRouter(
    tags=["pages"], include_in_schema=False, route_class=LoginRedirectRoute
)


def _template_context(user: User | None = None, **kwargs: object) -> dict:
    """Build common template context."""
    return {
        "user": user,
        "now": datetime.now(UTC),
        **kwargs,
    }


@router.get("/", response_class=HTMLResponse, summary="Home page")
async def home_page(
    request: Request,
    account: OptionalCurrentAccount,
) -> HTMLResponse:
    """Home page with phase overview."""
    phases = get_curriculum_overview()

    return templates.TemplateResponse(
        request,
        "pages/home.html",
        _template_context(user=account, phases=phases),
    )


@router.get("/curriculum", response_class=HTMLResponse, summary="Curriculum overview")
async def curriculum_page(
    request: Request,
    account: OptionalCurrentAccount,
) -> HTMLResponse:
    """Full curriculum overview with all phases and topics."""
    phases = get_curriculum_overview()

    return templates.TemplateResponse(
        request,
        "pages/curriculum.html",
        _template_context(user=account, phases=phases),
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
    account: CurrentAccount,
) -> HTMLResponse:
    """Single phase learning detail (requires auth)."""
    phase = get_phase_by_slug(f"phase{phase_id}")
    if phase is None:
        return templates.TemplateResponse(
            request,
            "pages/404.html",
            _template_context(user=account),
            status_code=404,
        )

    detail = await fetch_phase_progress(db, account.id, phase)
    topics = build_phase_topics(phase, detail)
    has_verification = bool(
        phase.hands_on_verification and phase.hands_on_verification.requirements
    )

    return templates.TemplateResponse(
        request,
        "pages/phase.html",
        _template_context(
            user=account,
            phase=phase,
            topics=topics,
            phase_progress=detail,
            has_verification=has_verification,
        ),
    )


@router.get(
    "/verifications",
    response_class=HTMLResponse,
    summary="Verification workspace",
)
async def verifications_page(
    request: Request,
    db: DbSession,
    account: CurrentAccount,
) -> HTMLResponse:
    """Verification progress and phase navigation (requires auth)."""
    overview = await get_verifications_overview(db, account.id)
    return templates.TemplateResponse(
        request,
        "pages/verifications.html",
        _template_context(user=account, overview=overview),
    )


@router.get(
    "/verifications/phase/{phase_id:int}",
    response_class=HTMLResponse,
    summary="Phase verification",
)
async def phase_verification_page(
    request: Request,
    phase_id: int,
    db: DbSession,
    account: CurrentAccount,
    history_page: Annotated[int, Query(ge=1)] = 1,
) -> HTMLResponse:
    """One phase's verification requirements and feedback (requires auth)."""
    phase = get_phase_by_slug(f"phase{phase_id}")
    if phase is None:
        return templates.TemplateResponse(
            request,
            "pages/404.html",
            _template_context(user=account),
            status_code=404,
        )

    workspace = await get_phase_verification_workspace(
        db,
        account.id,
        phase,
        account.github_username,
        history_page=history_page,
    )
    return templates.TemplateResponse(
        request,
        "pages/verification_phase.html",
        _template_context(
            user=account,
            phase=workspace.phase,
            phase_progress=workspace.phase_progress,
            requirements=workspace.requirements,
            card_contexts_by_req=workspace.card_contexts_by_req,
            verification_locked=workspace.verification_locked,
            prerequisite_phase_id=workspace.prerequisite_phase_id,
            history=workspace.history,
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
    account: CurrentAccount,
) -> HTMLResponse:
    """Single topic with learning steps (requires auth)."""
    phase_slug = f"phase{phase_id}"
    phase = get_phase_by_slug(phase_slug)
    topic = None
    if phase is not None:
        topic = next((t for t in phase.topics if t.slug == topic_slug), None)

    if phase is None or topic is None:
        return templates.TemplateResponse(
            request,
            "pages/404.html",
            _template_context(user=account),
            status_code=404,
        )

    completed_step_uuids = await get_valid_completed_steps(db, account.id, topic)

    all_topics = phase.topics
    prev_topic, next_topic = build_topic_nav(
        all_topics, topic_slug, phase_id, phase.name
    )

    total_steps = len(topic.learning_steps)
    progress = (
        build_progress_dict(len(completed_step_uuids), total_steps)
        if total_steps > 0
        else None
    )

    return templates.TemplateResponse(
        request,
        "pages/topic.html",
        _template_context(
            user=account,
            topic=topic,
            steps=topic.learning_steps,
            phase_name=phase.name,
            phase_id=phase.order,
            completed_steps=completed_step_uuids,
            prev_topic=prev_topic,
            next_topic=next_topic,
            progress=progress,
        ),
    )


@router.get("/dashboard", response_class=HTMLResponse, summary="User dashboard")
async def dashboard_page(
    request: Request,
    db: DbSession,
    account: CurrentAccount,
) -> HTMLResponse:
    """Authenticated dashboard with progress."""
    dashboard = await get_dashboard_data(db, account.id)

    return templates.TemplateResponse(
        request,
        "pages/dashboard.html",
        _template_context(
            user=account,
            dashboard=dashboard,
            help_links=HELP_LINKS,
        ),
    )


@router.get("/account", response_class=HTMLResponse, summary="Account settings")
async def account_page(
    request: Request,
    account: CurrentAccount,
) -> HTMLResponse:
    """Account settings page."""
    return templates.TemplateResponse(
        request,
        "pages/account.html",
        _template_context(user=account),
    )


@router.get("/community", response_class=HTMLResponse, summary="Community")
async def community_page(
    request: Request,
    db: DbSession,
    account: OptionalCurrentAccount,
) -> HTMLResponse:
    """Public community progress, graduates, and curriculum updates."""
    community = await get_community_page_data(db)

    return templates.TemplateResponse(
        request,
        "pages/community.html",
        _template_context(
            user=account,
            community=community,
            community_links=COMMUNITY_LINKS,
        ),
    )


@router.get("/stats", include_in_schema=False)
async def stats_page_redirect() -> RedirectResponse:
    """Redirect the former stats URL to the community page."""
    return RedirectResponse(url="/community", status_code=308)


@router.get("/faq", response_class=HTMLResponse, summary="FAQ")
async def faq_page(
    request: Request,
    account: OptionalCurrentAccount,
) -> HTMLResponse:
    """FAQ page."""
    return templates.TemplateResponse(
        request,
        "pages/faq.html",
        _template_context(user=account, faqs=FAQS),
    )


@router.get("/privacy", response_class=HTMLResponse, summary="Privacy policy")
async def privacy_page(
    request: Request,
    account: OptionalCurrentAccount,
) -> HTMLResponse:
    """Privacy policy page."""
    return templates.TemplateResponse(
        request,
        "pages/privacy.html",
        _template_context(user=account),
    )


@router.get("/terms", response_class=HTMLResponse, summary="Terms of service")
async def terms_page(
    request: Request,
    account: OptionalCurrentAccount,
) -> HTMLResponse:
    """Terms of service page."""
    return templates.TemplateResponse(
        request,
        "pages/terms.html",
        _template_context(user=account),
    )
