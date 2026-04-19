"""Repository for aggregate analytics queries.

All queries return anonymous, aggregate data only — no individual user
information is exposed.
"""

from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from models import StepProgress, Submission, User


class AnalyticsRepository:
    """Repository for read-only aggregate analytics queries."""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def get_total_users(self) -> int:
        """Count total registered users."""
        result = await self.db.execute(select(func.count()).select_from(User))
        return result.scalar_one() or 0

    async def get_active_learners(self, days: int = 30) -> int:
        """Count users with any learning activity in the last N days.

        Includes users who completed reading steps OR submitted
        verification attempts — not just step_progress alone.
        """
        cutoff = datetime.now(UTC) - timedelta(days=days)

        step_users = select(StepProgress.user_id).where(
            StepProgress.completed_at >= cutoff,
        )
        submission_users = select(Submission.user_id).where(
            Submission.created_at >= cutoff,
        )
        combined = step_users.union(submission_users).subquery()

        result = await self.db.execute(select(func.count()).select_from(combined))
        return result.scalar_one() or 0
