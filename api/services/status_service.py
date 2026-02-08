"""System status service.

Combines a simple health check with community analytics into a
public status page payload.  Only exposes "operational" /
"degraded" / "down" — no infrastructure internals like pool
metrics, versions, or component breakdowns.
"""

import logging
from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from core.database import comprehensive_health_check
from schemas import SystemStatus
from services.analytics_service import get_community_analytics

logger = logging.getLogger(__name__)


async def get_system_status(
    engine: AsyncEngine,
    db: AsyncSession,
) -> SystemStatus:
    """Build the public status page payload.

    Performs a quick health check to determine the overall status
    indicator, then attaches community analytics.  No infrastructure
    details are exposed.
    """
    now = datetime.now(UTC)

    # --- Health check (fast — just SELECT 1 + optional token check) ---
    health = await comprehensive_health_check(engine)

    db_ok = health["database"]
    auth_ok = health.get("azure_auth")  # None when not using Azure

    if not db_ok or auth_ok is False:
        overall = "down"
    else:
        overall = "operational"

    # --- Analytics (may fail independently of health) ---
    try:
        analytics = await get_community_analytics(db)
    except Exception:
        logger.exception("status.analytics_failed")
        from schemas import CommunityAnalytics

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
            top_topics=[],
            generated_at=now,
        )

    return SystemStatus(
        overall_status=overall,
        analytics=analytics,
        checked_at=now,
    )
