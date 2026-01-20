"""Dashboard and content endpoints.

These endpoints provide:
- Dashboard data (user + phases + progress)
- Phase listings and details
- Topic details with steps and questions

All progress calculation and locking logic follows
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


@router.get("/dashboard", response_model=DashboardResponse)
@limiter.limit("30/minute")
async def get_dashboard_endpoint(
    request: Request,
    user_id: UserId,
    db: DbSession,
) -> DashboardResponse:
    """Get complete dashboard data for the current user.

    Returns:
    - User info
    - All phases with progress and locking status
    - Overall progress statistics
    """
    user = await get_or_create_user(db, user_id)

    dashboard = await get_dashboard(
        db=db,
        user_id=user_id,
        user_email=user.email,
        user_first_name=user.first_name,
        user_last_name=user.last_name,
        user_avatar_url=user.avatar_url,
        user_github_username=user.github_username,
        is_admin=user.is_admin,
    )

    # Service returns Pydantic model
    return DashboardResponse.model_validate(dashboard.model_dump())


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
    - Locking status based on completion

    For unauthenticated users:
    - No progress (all null)
    - Only Phase 0 unlocked, rest locked

    Returns phases in order (0-6).
    """
    if user_id:
        user = await get_or_create_user(db, user_id)
        phases = await get_phases_list(db, user_id, user.is_admin)
    else:
        # Unauthenticated: return phases without progress
        phases = await get_phases_list(db, None, False)

    # Service returns list of Pydantic models
    return [PhaseSummarySchema.model_validate(phase.model_dump()) for phase in phases]


@router.get("/phases/{phase_slug}", response_model=PhaseDetailSchema)
@limiter.limit("30/minute")
async def get_phase_detail_endpoint(
    request: Request,
    phase_slug: str,
    user_id: OptionalUserId,
    db: DbSession,
) -> PhaseDetailSchema:
    """Get detailed phase info with topics.

    Returns:
    - Phase info and objectives
    - Topics with progress and locking status
    - Hands-on requirements and submissions

    For unauthenticated users:
    - No progress data
    - First topic unlocked, rest locked (if phase is accessible)
    """
    is_admin = False
    if user_id:
        user = await get_or_create_user(db, user_id)
        is_admin = user.is_admin

    phase_detail = await get_phase_detail(db, user_id, phase_slug, is_admin)

    if phase_detail is None:
        raise HTTPException(status_code=404, detail="Phase not found")

    # Service returns Pydantic model
    return PhaseDetailSchema.model_validate(phase_detail.model_dump())


@router.get(
    "/phases/{phase_slug}/topics/{topic_slug}",
    response_model=TopicDetailSchema,
)
@limiter.limit("30/minute")
async def get_topic_detail_endpoint(
    request: Request,
    phase_slug: str,
    topic_slug: str,
    user_id: OptionalUserId,
    db: DbSession,
) -> TopicDetailSchema:
    """Get detailed topic info with steps and questions.

    Returns:
    - Topic info
    - Learning steps
    - Knowledge questions
    - Progress (completed steps, passed questions)
    - Locking status

    For unauthenticated users:
    - No progress data
    - Content shown but cannot be interacted with
    """
    is_admin = False
    if user_id:
        user = await get_or_create_user(db, user_id)
        is_admin = user.is_admin

    topic_detail = await get_topic_detail(db, user_id, phase_slug, topic_slug, is_admin)

    if topic_detail is None:
        raise HTTPException(status_code=404, detail="Topic not found")

    # Service returns Pydantic model
    return TopicDetailSchema.model_validate(topic_detail.model_dump())
