"""Activity service for streak calculation, heatmap data, and activity logging.

This module handles:
- Activity logging (the single point for recording user activities)
- Streak calculation with forgiveness rules
- Heatmap data aggregation for profile display

Routes should use this service for all activity-related business logic.
"""

from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta

from sqlalchemy.ext.asyncio import AsyncSession

from models import ActivityType
from repositories.activity_repository import ActivityRepository
from services.streaks_service import MAX_SKIP_DAYS, calculate_streak_with_forgiveness


@dataclass
class StreakData:
    """User's streak information."""

    current_streak: int
    longest_streak: int
    total_activity_days: int
    last_activity_date: date | None
    streak_alive: bool


@dataclass
class HeatmapDay:
    """Activity data for a single day."""

    date: date
    count: int
    activity_types: list[str]


@dataclass
class HeatmapData:
    """Activity heatmap data for profile display."""

    days: list[HeatmapDay]
    start_date: date
    end_date: date
    total_activities: int


async def get_streak_data(db, user_id: str) -> StreakData:
    """Calculate user's streak information.

    Streak calculation allows up to 2 skipped days per week.
    Uses limited query (100 dates) for performance - sufficient for streak calc.
    """
    activity_repo = ActivityRepository(db)
    # Limit to 100 dates for performance - more than enough for streak calculation
    # since a 3+ day gap breaks the streak anyway
    activity_dates = await activity_repo.get_activity_dates_ordered(user_id, limit=100)

    current_streak, longest_streak, streak_alive = calculate_streak_with_forgiveness(
        activity_dates, MAX_SKIP_DAYS
    )

    unique_dates = set(activity_dates)
    total_activity_days = len(unique_dates)

    last_activity_date = activity_dates[0] if activity_dates else None

    return StreakData(
        current_streak=current_streak,
        longest_streak=longest_streak,
        total_activity_days=total_activity_days,
        last_activity_date=last_activity_date,
        streak_alive=streak_alive,
    )


async def get_heatmap_data(db, user_id: str, days: int = 365) -> HeatmapData:
    """Get activity heatmap data for profile display.

    Returns activity counts per day for the specified number of days.
    Similar to GitHub's contribution graph.
    """
    today = datetime.now(UTC).date()
    start_date = today - timedelta(days=days)

    activity_repo = ActivityRepository(db)
    rows = await activity_repo.get_heatmap_data(user_id, start_date)

    date_activities: dict[str, dict] = {}
    total_activities = 0

    for activity_date, activity_type, count in rows:
        date_str = activity_date.isoformat()
        if date_str not in date_activities:
            date_activities[date_str] = {"count": 0, "types": set()}
        date_activities[date_str]["count"] += count
        date_activities[date_str]["types"].add(activity_type)
        total_activities += count

    heatmap_days = []
    for date_str, data in date_activities.items():
        heatmap_days.append(
            HeatmapDay(
                date=datetime.fromisoformat(date_str).date(),
                count=data["count"],
                activity_types=list(data["types"]),
            )
        )

    return HeatmapData(
        days=heatmap_days,
        start_date=start_date,
        end_date=today,
        total_activities=total_activities,
    )


@dataclass
class ActivityResult:
    """Result of logging an activity."""

    id: int
    activity_type: ActivityType
    activity_date: date
    reference_id: str | None
    created_at: datetime


async def log_activity(
    db: AsyncSession,
    user_id: str,
    activity_type: ActivityType,
    reference_id: str | None = None,
) -> ActivityResult:
    """Log a user activity for streak and heatmap tracking.

    Args:
        db: Database session
        user_id: The user's ID
        activity_type: Type of activity being logged
        reference_id: Optional reference (e.g., topic_id, question_id)

    Returns:
        ActivityResult with the created activity details
    """
    today = datetime.now(UTC).date()

    activity_repo = ActivityRepository(db)
    activity = await activity_repo.log_activity(
        user_id=user_id,
        activity_type=activity_type,
        activity_date=today,
        reference_id=reference_id,
    )

    return ActivityResult(
        id=activity.id,
        activity_type=activity.activity_type,
        activity_date=activity.activity_date,
        reference_id=activity.reference_id,
        created_at=activity.created_at,
    )
