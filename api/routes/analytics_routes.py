"""Community analytics routes.

Public endpoints — no authentication required. All data is aggregate
and anonymous, safe for public dashboards and conference presentations.
"""

import logging
from datetime import UTC, datetime

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse

from core.auth import OptionalUserId
from core.database import DbSessionReadOnly, comprehensive_health_check
from schemas import CommunityAnalytics
from services.analytics_service import get_community_analytics

logger = logging.getLogger(__name__)

router = APIRouter(tags=["analytics"])


@router.get("/status", response_class=HTMLResponse, include_in_schema=False)
async def status_page(
    request: Request,
    db: DbSessionReadOnly,
    user_id: OptionalUserId,
) -> HTMLResponse:
    """Public status page with system health and community analytics."""
    from services.users_service import get_user_by_id

    user = None
    if user_id is not None:
        user = await get_user_by_id(db, user_id)

    health = await comprehensive_health_check(request.app.state.engine)
    db_ok = health["database"]
    auth_ok = health.get("azure_auth")  # None when not using Azure
    overall_status = "down" if (not db_ok or auth_ok is False) else "operational"

    try:
        analytics = await get_community_analytics(db)
    except Exception:
        logger.exception("status_page.analytics_failed")
        analytics = CommunityAnalytics(
            total_users=0,
            total_certificates=0,
            active_learners_30d=0,
            completion_rate=0.0,
            phase_distribution=[],
            signup_trends=[],
            certificate_trends=[],
            verification_stats=[],
            activity_by_day=[],
            generated_at=datetime.now(UTC),
        )

    return request.app.state.templates.TemplateResponse(
        "pages/status.html",
        {
            "request": request,
            "user": user,
            "overall_status": overall_status,
            "analytics": analytics,
            "checked_at": datetime.now(UTC),
            "now": datetime.now(UTC),
        },
    )
