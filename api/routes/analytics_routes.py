"""Community analytics and system status routes.

Public endpoints — no authentication required. All data is aggregate
and anonymous, safe for public dashboards and conference presentations.
"""

from datetime import UTC, datetime

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse

from core.auth import OptionalUserId
from core.database import DbSession
from core.ratelimit import limiter
from schemas import CommunityAnalytics, SystemStatus
from services.analytics_service import get_community_analytics
from services.status_service import get_system_status

router = APIRouter(tags=["analytics"])


# ── JSON APIs (literal paths before parameterized) ──


@router.get(
    "/api/status",
    response_model=SystemStatus,
    summary="System status with health and analytics",
    responses={429: {"description": "Rate limit exceeded"}},
)
@limiter.limit("10/minute")
async def system_status_api(
    request: Request,
    db: DbSession,
) -> SystemStatus:
    """Return system health and aggregate community analytics.

    Combines infrastructure health checks with anonymous trend data.
    Designed for status page integrations and monitoring dashboards.
    """
    return await get_system_status(request.app.state.engine, db)


@router.get(
    "/api/analytics/community",
    response_model=CommunityAnalytics,
    summary="Aggregate community analytics",
    responses={429: {"description": "Rate limit exceeded"}},
)
@limiter.limit("10/minute")
async def community_analytics_api(
    request: Request,
    db: DbSession,
) -> CommunityAnalytics:
    """Return aggregate, anonymous community analytics.

    Designed for programmatic access — conference slides, data exports,
    and external dashboards. All data is privacy-safe.
    """
    return await get_community_analytics(db)


# ── HTML page ──


@router.get("/status", response_class=HTMLResponse, include_in_schema=False)
async def status_page(
    request: Request,
    db: DbSession,
    user_id: OptionalUserId,
) -> HTMLResponse:
    """Public status page with system health and community analytics."""
    from services.users_service import get_user_by_id

    user = None
    if user_id is not None:
        user = await get_user_by_id(db, user_id)

    status = await get_system_status(request.app.state.engine, db)

    return request.app.state.templates.TemplateResponse(
        "pages/status.html",
        {
            "request": request,
            "user": user,
            "status": status,
            "analytics": status.analytics,
            "now": datetime.now(UTC),
        },
    )
