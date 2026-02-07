"""Repository for activity tracking operations."""

from collections.abc import Sequence
from datetime import date

from sqlalchemy import exists, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from models import ActivityType, UserActivity


class ActivityRepository:
    """Repository for user activity operations (streak tracking, etc.)."""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def get_by_user(
        self,
        user_id: int,
        *,
        limit: int | None = None,
        cursor: int | None = None,
    ) -> Sequence[UserActivity]:
        """Get activities for a user, most recent first.

        Args:
            user_id: The user's ID
            limit: Maximum number of activities to return
            cursor: Activity ID to start after (for pagination).
                    Pass the last activity's ID from previous page.
        """
        query = (
            select(UserActivity)
            .where(UserActivity.user_id == user_id)
            .order_by(UserActivity.created_at.desc(), UserActivity.id.desc())
        )
        if cursor:
            query = query.where(UserActivity.id < cursor)
        if limit:
            query = query.limit(limit)
        result = await self.db.execute(query)
        return result.scalars().all()

    async def get_activities_in_range(
        self,
        user_id: int,
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
        user_id: int,
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
        user_id: int,
        activity_type: ActivityType,
    ) -> int:
        """Count activities of a specific type for a user."""
        result = await self.db.execute(
            select(func.count(UserActivity.id)).where(
                UserActivity.user_id == user_id,
                UserActivity.activity_type == activity_type,
            )
        )
        return result.scalar_one()

    async def has_activity_on_date(
        self,
        user_id: int,
        activity_date: date,
    ) -> bool:
        """Check if user has any activity on a specific date."""
        stmt = exists().where(
            UserActivity.user_id == user_id,
            UserActivity.activity_date == activity_date,
        )
        result = await self.db.execute(select(stmt))
        return result.scalar_one()

    async def get_activity_dates_ordered(
        self,
        user_id: int,
        *,
        limit: int | None = None,
    ) -> list[date]:
        """Get distinct activity dates for a user ordered by date descending.

        Args:
            user_id: The user's ID
            limit: Maximum number of dates to return (for performance).
                   For streak calculation, ~100 is typically sufficient.
        """
        query = (
            select(func.distinct(UserActivity.activity_date))
            .where(UserActivity.user_id == user_id)
            .order_by(UserActivity.activity_date.desc())
        )
        if limit:
            query = query.limit(limit)
        result = await self.db.execute(query)
        return [row[0] for row in result.all()]
