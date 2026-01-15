"""Repository for activity tracking operations."""

from collections.abc import Sequence
from datetime import date

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from models import ActivityType, UserActivity


class ActivityRepository:
    """Repository for user activity operations (streak tracking, etc.)."""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def get_by_user(
        self,
        user_id: str,
        *,
        limit: int | None = None,
    ) -> Sequence[UserActivity]:
        """Get activities for a user, most recent first."""
        query = (
            select(UserActivity)
            .where(UserActivity.user_id == user_id)
            .order_by(UserActivity.created_at.desc())
        )
        if limit:
            query = query.limit(limit)
        result = await self.db.execute(query)
        return result.scalars().all()

    async def get_activity_dates(
        self,
        user_id: str,
    ) -> set[date]:
        """Get all unique activity dates for a user."""
        result = await self.db.execute(
            select(UserActivity.activity_date)
            .where(UserActivity.user_id == user_id)
            .distinct()
        )
        return set(row[0] for row in result.all() if row[0] is not None)

    async def get_activities_in_range(
        self,
        user_id: str,
        start_date: date,
        end_date: date,
    ) -> Sequence[UserActivity]:
        """Get activities for a user within a date range."""
        result = await self.db.execute(
            select(UserActivity)
            .where(
                UserActivity.user_id == user_id,
                UserActivity.activity_date >= start_date,
                UserActivity.activity_date <= end_date,
            )
            .order_by(UserActivity.activity_date.desc())
        )
        return result.scalars().all()

    async def log_activity(
        self,
        user_id: str,
        activity_type: ActivityType,
        activity_date: date,
        reference_id: str | None = None,
    ) -> UserActivity:
        """Log a new user activity."""
        activity = UserActivity(
            user_id=user_id,
            activity_type=activity_type,
            activity_date=activity_date,
            reference_id=reference_id,
        )
        self.db.add(activity)
        await self.db.flush()
        return activity

    async def count_by_type(
        self,
        user_id: str,
        activity_type: ActivityType,
    ) -> int:
        """Count activities of a specific type for a user."""
        from sqlalchemy import func

        result = await self.db.execute(
            select(func.count(UserActivity.id)).where(
                UserActivity.user_id == user_id,
                UserActivity.activity_type == activity_type,
            )
        )
        return result.scalar_one() or 0

    async def has_activity_on_date(
        self,
        user_id: str,
        activity_date: date,
    ) -> bool:
        """Check if user has any activity on a specific date."""
        result = await self.db.execute(
            select(UserActivity.id).where(
                UserActivity.user_id == user_id,
                UserActivity.activity_date == activity_date,
            )
        )
        return result.scalar_one_or_none() is not None

    async def get_activity_dates_ordered(
        self,
        user_id: str,
    ) -> list[date]:
        """Get all activity dates for a user ordered by date descending."""
        result = await self.db.execute(
            select(UserActivity.activity_date)
            .where(UserActivity.user_id == user_id)
            .order_by(UserActivity.activity_date.desc())
        )
        return [row[0] for row in result.all()]

    async def get_heatmap_data(
        self,
        user_id: str,
        start_date: date,
    ) -> list[tuple[date, str, int]]:
        """Get activity data grouped by date and type for heatmap display.

        Returns list of (activity_date, activity_type, count) tuples.
        """
        from sqlalchemy import func

        result = await self.db.execute(
            select(
                UserActivity.activity_date,
                UserActivity.activity_type,
                func.count(UserActivity.id).label("count"),
            )
            .where(
                UserActivity.user_id == user_id,
                UserActivity.activity_date >= start_date,
            )
            .group_by(UserActivity.activity_date, UserActivity.activity_type)
            .order_by(UserActivity.activity_date)
        )
        return [(row[0], row[1], row[2]) for row in result.all()]
