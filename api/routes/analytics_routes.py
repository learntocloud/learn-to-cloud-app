"""Community analytics routes.

Public endpoints — no authentication required. All data is aggregate
and anonymous.
"""

import logging
from datetime import UTC, datetime

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse

from core.auth import OptionalUserId
from core.database import DbSessionReadOnly, comprehensive_health_check
from core.ratelimit import limiter
from core.templates import templates
from schemas import CommunityAnalytics
from services.analytics_service import get_community_analytics
from services.users_service import get_user_by_id

logger = logging.getLogger(__name__)

router = APIRouter(tags=["analytics"])


@router.get("/status", response_class=HTMLResponse, include_in_schema=False)
@limiter.limit("30/minute")
async def status_page(
    request: Request,
    db: DbSessionReadOnly,
    user_id: OptionalUserId,
) -> HTMLResponse:
    """Public status page with system health and key metrics."""
    user = None
    if user_id is not None:
        user = await get_user_by_id(db, user_id)

    health = await comprehensive_health_check(request.app.state.engine)
    db_ok = health["database"]
    auth_ok = health.get("azure_auth")
    overall_status = "down" if (not db_ok or auth_ok is False) else "operational"

    try:
        analytics = await get_community_analytics(db)
    except Exception as exc:
        logger.error(
            "status_page.analytics_failed",
            extra={
                "exc_type": type(exc).__name__,
                "exc_message": str(exc),
            },
        )
        analytics = CommunityAnalytics(
            total_users=0,
            active_learners_30d=0,
            generated_at=datetime.now(UTC),
        )

    return templates.TemplateResponse(
        request,
        "pages/status.html",
        {
            "user": user,
            "overall_status": overall_status,
            "analytics": analytics,
            "checked_at": datetime.now(UTC),
            "now": datetime.now(UTC),
        },
    )
