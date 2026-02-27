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
from core.templates import templates
from schemas import CommunityAnalytics
from services.analytics_service import get_community_analytics
from services.users_service import get_user_by_id

logger = logging.getLogger(__name__)

router = APIRouter(tags=["analytics"])


def _derive_insights(
    analytics: CommunityAnalytics,
) -> list[dict[str, str]]:
    insights: list[dict[str, str]] = []
    if analytics.activity_by_day:
        busiest = max(
            analytics.activity_by_day,
            key=lambda d: d.completions,
        )
        if busiest.completions > 0:
            insights.append(
                {
                    "text": f"Most active day: {busiest.day_name}",
                    "detail": f"{busiest.completions:,} steps completed",
                }
            )
    if analytics.verification_stats:
        hardest = min(
            (v for v in analytics.verification_stats if v.total_attempts > 0),
            key=lambda v: v.pass_rate,
            default=None,
        )
        if hardest:
            insights.append(
                {
                    "text": f"Hardest phase: {hardest.phase_name}",
                    "detail": f"{hardest.pass_rate}% pass rate",
                }
            )
    if analytics.provider_distribution:
        top = max(
            analytics.provider_distribution,
            key=lambda p: p.count,
        )
        total = sum(p.count for p in analytics.provider_distribution)
        pct = round(top.count / total * 100) if total > 0 else 0
        insights.append(
            {
                "text": f"Top provider: {top.provider.upper()}",
                "detail": f"{pct}% of submissions",
            }
        )
    return insights


@router.get("/status", response_class=HTMLResponse, include_in_schema=False)
async def status_page(
    request: Request,
    db: DbSessionReadOnly,
    user_id: OptionalUserId,
) -> HTMLResponse:
    """Public status page with system health and community analytics."""
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
            active_learners_30d=0,
            completion_rate=0.0,
            phase_distribution=[],
            signup_trends=[],
            verification_stats=[],
            activity_by_day=[],
            generated_at=datetime.now(UTC),
        )

    insights = _derive_insights(analytics)

    # Only show "new this month" if the latest trend entry is the current month.
    current_month = datetime.now(UTC).strftime("%Y-%m")
    new_this_month = 0
    if analytics.signup_trends and analytics.signup_trends[-1].month == current_month:
        new_this_month = analytics.signup_trends[-1].count

    return templates.TemplateResponse(
        "pages/status.html",
        {
            "request": request,
            "user": user,
            "overall_status": overall_status,
            "analytics": analytics,
            "insights": insights,
            "new_this_month": new_this_month,
            "checked_at": datetime.now(UTC),
            "now": datetime.now(UTC),
        },
    )
