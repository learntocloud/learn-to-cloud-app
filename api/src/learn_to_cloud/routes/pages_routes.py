"""Page routes — server-side rendered HTML pages.

These routes serve full Jinja2 pages. They call the same services as the
JSON API routes but render HTML templates instead of returning JSON.
"""

import logging
from datetime import UTC, datetime

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from learn_to_cloud_shared.content_service import (
    get_curriculum_overview,
    get_phase_by_slug,
)
from learn_to_cloud_shared.core.database import DbSession
from learn_to_cloud_shared.models import User
from learn_to_cloud_shared.repositories.verification_attempt_repository import (
    VerificationAttemptRepository,
)
from learn_to_cloud_shared.requirements import (
    is_phase_verification_locked,
)

from learn_to_cloud.core.auth import OptionalUserId, UserId
from learn_to_cloud.core.templates import templates
from learn_to_cloud.rendering.context import (
    COMMUNITY_LINKS,
    FAQS,
    HELP_LINKS,
    build_phase_topics,
    build_progress_dict,
    build_requirement_card_context,
    build_topic_nav,
    feedback_tasks_and_passed,
)
from learn_to_cloud.services.community_service import get_community_page_data
from learn_to_cloud.services.dashboard_service import get_dashboard_data
from learn_to_cloud.services.progress_service import fetch_phase_progress
from learn_to_cloud.services.steps_service import get_valid_completed_steps
from learn_to_cloud.services.submissions_service import get_phase_submission_context
from learn_to_cloud.services.users_service import get_user_by_id
from learn_to_cloud.services.verification_status_tokens import (
    create_verification_status_token,
)

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
    phases = get_curriculum_overview()

    return templates.TemplateResponse(
        request,
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
    phases = get_curriculum_overview()

    return templates.TemplateResponse(
        request,
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
            request,
            "pages/404.html",
            _template_context(request, user=user),
            status_code=404,
        )

    detail = await fetch_phase_progress(db, user_id, phase)
    topics = build_phase_topics(phase, detail)

    requirements = []
    hands_on = phase.hands_on_verification
    if hands_on:
        requirements = hands_on.requirements

    sub_context = await get_phase_submission_context(db, user_id, phase)
    submissions_by_req = sub_context.submissions_by_req
    feedback_by_req = sub_context.feedback_by_req
    requirements_by_uuid = {req.uuid: req for req in requirements}
    active_attempts = await VerificationAttemptRepository(
        db
    ).get_active_for_requirements(
        user_id,
        requirements_by_uuid.keys(),
    )
    active_jobs_by_req = {
        requirements_by_uuid[attempt.requirement_uuid].slug: attempt
        for attempt in active_attempts
        if attempt.requirement_uuid in requirements_by_uuid
    }
    # The Durable orchestration instance id is the attempt UUID, so the status
    # token keys off that same id.
    verification_status_tokens_by_req = {
        requirements_by_uuid[attempt.requirement_uuid].slug: (
            create_verification_status_token(
                user_id=user_id,
                job_id=attempt.id,
                instance_id=str(attempt.id),
                requirement_slug=requirements_by_uuid[attempt.requirement_uuid].slug,
            )
        )
        for attempt in active_attempts
        if attempt.requirement_uuid in requirements_by_uuid
    }

    # Pre-compute one verification-card context per requirement -- derived
    # URL, card state, and banner text all in one place, so the template
    # never re-derives a card's flags from raw submission fields (also the
    # single source of truth the locked and unlocked branches both read).
    github_username = user.github_username if user else None
    card_contexts_by_req: dict[str, dict] = {}
    for req in requirements:
        feedback_tasks, feedback_passed = feedback_tasks_and_passed(
            feedback_by_req.get(req.slug)
        )
        active_job = active_jobs_by_req.get(req.slug)
        card_contexts_by_req[req.slug] = build_requirement_card_context(
            requirement=req,
            github_username=github_username,
            submission=submissions_by_req.get(req.slug),
            feedback_tasks=feedback_tasks,
            feedback_passed=feedback_passed,
            processing=active_job is not None,
            verification_status_token=verification_status_tokens_by_req.get(req.slug),
        )

    # Sequential phase gating — check if prerequisite phase is complete
    verification_locked, prerequisite_phase_id = await is_phase_verification_locked(
        db, user_id, phase_id
    )

    return templates.TemplateResponse(
        request,
        "pages/phase.html",
        _template_context(
            request,
            user=user,
            phase=phase,
            topics=topics,
            requirements=requirements,
            card_contexts_by_req=card_contexts_by_req,
            phase_progress=detail,
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
    topic = None
    if phase is not None:
        topic = next((t for t in phase.topics if t.slug == topic_slug), None)

    if phase is None or topic is None:
        return templates.TemplateResponse(
            request,
            "pages/404.html",
            _template_context(request, user=user),
            status_code=404,
        )

    completed_step_uuids = await get_valid_completed_steps(db, user_id, topic)

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
            request,
            user=user,
            topic=topic,
            steps=topic.learning_steps,
            phase_slug=phase_slug,
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
    user_id: UserId,
) -> HTMLResponse:
    """Authenticated dashboard with progress."""
    user = await _get_user_or_none(db, user_id)
    if user is None:
        return templates.TemplateResponse(
            request,
            "pages/404.html",
            _template_context(request),
            status_code=404,
        )

    dashboard = await get_dashboard_data(db, user_id)

    return templates.TemplateResponse(
        request,
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
            request,
            "pages/404.html",
            _template_context(request),
            status_code=404,
        )

    return templates.TemplateResponse(
        request,
        "pages/account.html",
        _template_context(request, user=user),
    )


@router.get("/community", response_class=HTMLResponse, summary="Community")
async def community_page(
    request: Request,
    db: DbSession,
    user_id: OptionalUserId,
) -> HTMLResponse:
    """Public community progress, graduates, and curriculum updates."""
    user = await _get_user_or_none(db, user_id)
    community = await get_community_page_data(db)

    return templates.TemplateResponse(
        request,
        "pages/community.html",
        _template_context(
            request,
            user=user,
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
    db: DbSession,
    user_id: OptionalUserId,
) -> HTMLResponse:
    """FAQ page."""
    user = await _get_user_or_none(db, user_id)

    return templates.TemplateResponse(
        request,
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
        request,
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
        request,
        "pages/terms.html",
        _template_context(request, user=user),
    )
