"""Community analytics service.

Runs two cheap indexed COUNT queries on demand for the public status page.
No background loop, no snapshot table, no in-memory cache.
"""

import logging
from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession

from repositories.analytics_repository import AnalyticsRepository
from schemas import CommunityAnalytics

logger = logging.getLogger(__name__)


async def get_community_analytics(db: AsyncSession) -> CommunityAnalytics:
    """Compute community analytics from live data.

    Runs two simple aggregate queries — cheap enough for every page load.
    """
    repo = AnalyticsRepository(db)
    total_users = await repo.get_total_users()
    active_30d = await repo.get_active_learners(days=30)

    return CommunityAnalytics(
        total_users=total_users,
        active_learners_30d=active_30d,
        generated_at=datetime.now(UTC),
    )
