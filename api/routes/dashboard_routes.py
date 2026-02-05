"""Dashboard and content endpoints.

These endpoints provide:
- Dashboard data (user + phases + progress)
- Phase listings and details
- Topic details with steps

All progress calculation follows
.github/skills/progression-system/progression-system.md
"""

from fastapi import APIRouter, HTTPException, Request

from core import get_logger
from core.auth import OptionalUserId, UserId
from core.database import DbSession
from core.ratelimit import limiter
from schemas import (
    DashboardResponse,
    PhaseDetailSchema,
    PhaseSummarySchema,
    TopicDetailSchema,
)
from services.dashboard_service import (
    get_dashboard,
    get_phase_detail,
    get_phases_list,
    get_topic_detail,
)
from services.users_service import get_or_create_user

logger = get_logger(__name__)

router = APIRouter(prefix="/api/user", tags=["dashboard"])


@router.get(
    "/dashboard",
    response_model=DashboardResponse,
    responses={401: {"description": "Not authenticated"}},
)
@limiter.limit("30/minute")
async def get_dashboard_endpoint(
    request: Request,
    user_id: UserId,
    db: DbSession,
) -> DashboardResponse:
    """Get complete dashboard data for the current user."""
    user = await get_or_create_user(db, user_id)

    return await get_dashboard(
        db=db,
        user_id=user_id,
        user_email=user.email,
        user_first_name=user.first_name,
        user_last_name=user.last_name,
        user_avatar_url=user.avatar_url,
        user_github_username=user.github_username,
        is_admin=user.is_admin,
    )


@router.get("/phases", response_model=list[PhaseSummarySchema])
@limiter.limit("30/minute")
async def get_phases_endpoint(
    request: Request,
    user_id: OptionalUserId,
    db: DbSession,
) -> list[PhaseSummarySchema]:
    """Get all phases with progress for the current user.

    For authenticated users:
    - Progress statistics

    For unauthenticated users:
    - No progress (all null)

    Returns phases in order (0-6).
    """
    if user_id:
        await get_or_create_user(db, user_id)
        return await get_phases_list(db, user_id)

    return await get_phases_list(db, None)


@router.get(
    "/phases/{phase_slug}",
    response_model=PhaseDetailSchema,
    responses={404: {"description": "Phase not found"}},
)
@limiter.limit("30/minute")
async def get_phase_detail_endpoint(
    request: Request,
    phase_slug: str,
    user_id: OptionalUserId,
    db: DbSession,
) -> PhaseDetailSchema:
    """Get detailed phase info with topics.

    Unauthenticated: no progress, content is read-only.
    """
    if user_id:
        await get_or_create_user(db, user_id)

    phase_detail = await get_phase_detail(db, user_id, phase_slug)

    if phase_detail is None:
        raise HTTPException(status_code=404, detail="Phase not found")

    return phase_detail


@router.get(
    "/phases/{phase_slug}/topics/{topic_slug}",
    response_model=TopicDetailSchema,
    responses={404: {"description": "Topic or phase not found"}},
)
@limiter.limit("30/minute")
async def get_topic_detail_endpoint(
    request: Request,
    phase_slug: str,
    topic_slug: str,
    user_id: OptionalUserId,
    db: DbSession,
) -> TopicDetailSchema:
    """Get detailed topic info with steps.

    Unauthenticated: no progress, content is read-only.
    """
    if user_id:
        await get_or_create_user(db, user_id)

    topic_detail = await get_topic_detail(db, user_id, phase_slug, topic_slug)

    if topic_detail is None:
        raise HTTPException(status_code=404, detail="Topic not found")

    return topic_detail
