"""Activity tracking and streak calculation endpoints."""

import logging
from datetime import UTC, datetime, timedelta

from fastapi import APIRouter
from sqlalchemy import func, select

from shared.auth import UserId
from shared.database import DbSession
from shared.models import UserActivity
from shared.schemas import (
    ActivityHeatmapDay,
    ActivityHeatmapResponse,
    ActivityLogRequest,
    ActivityResponse,
    StreakResponse,
)
from shared.streaks import MAX_SKIP_DAYS, calculate_streak_with_forgiveness

from .users import get_or_create_user

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/activity", tags=["activity"])


@router.post("/log", response_model=ActivityResponse)
async def log_activity(
    activity: ActivityLogRequest,
    user_id: UserId,
    db: DbSession,
) -> ActivityResponse:
    """Manually log a user activity.

    Note: Most activities are logged automatically by other endpoints
    (question attempts, reflections, topic completions).
    """
    await get_or_create_user(db, user_id)

    today = datetime.now(UTC).date()

    new_activity = UserActivity(
        user_id=user_id,
        activity_type=activity.activity_type,
        activity_date=today,
        reference_id=activity.reference_id,
    )
    db.add(new_activity)
    await db.commit()
    await db.refresh(new_activity)

    return ActivityResponse(
        id=new_activity.id,
        activity_type=new_activity.activity_type,
        activity_date=new_activity.activity_date,
        reference_id=new_activity.reference_id,
        created_at=new_activity.created_at,
    )


@router.get("/streak", response_model=StreakResponse)
async def get_user_streak(
    user_id: UserId,
    db: DbSession,
) -> StreakResponse:
    """Get the user's current streak information.

    Streak calculation allows up to 2 skipped days per week.
    """
    await get_or_create_user(db, user_id)

    # Get all activity dates for this user
    result = await db.execute(
        select(UserActivity.activity_date)
        .where(UserActivity.user_id == user_id)
        .order_by(UserActivity.activity_date.desc())
    )
    activity_dates = [row[0] for row in result.all()]

    # Calculate streaks
    current_streak, longest_streak, streak_alive = calculate_streak_with_forgiveness(
        activity_dates, MAX_SKIP_DAYS
    )

    # Get unique days count
    unique_dates = set(activity_dates)
    total_activity_days = len(unique_dates)

    # Get most recent activity date
    last_activity_date = activity_dates[0] if activity_dates else None

    return StreakResponse(
        current_streak=current_streak,
        longest_streak=longest_streak,
        total_activity_days=total_activity_days,
        last_activity_date=last_activity_date,
        streak_alive=streak_alive,
    )


@router.get("/heatmap", response_model=ActivityHeatmapResponse)
async def get_activity_heatmap(
    user_id: UserId,
    db: DbSession,
    days: int = 365,
) -> ActivityHeatmapResponse:
    """Get activity heatmap data for profile display.

    Returns activity counts per day for the specified number of days.
    Similar to GitHub's contribution graph.
    """
    await get_or_create_user(db, user_id)

    today = datetime.now(UTC).date()
    start_date = today - timedelta(days=days)

    # Get activities grouped by date
    result = await db.execute(
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
    rows = result.all()

    # Aggregate by date
    date_activities: dict[str, dict] = {}
    total_activities = 0

    for row in rows:
        date_str = row.activity_date.isoformat()
        if date_str not in date_activities:
            date_activities[date_str] = {"count": 0, "types": set()}
        # row[2] is the count column from the query
        row_count: int = row[2]
        date_activities[date_str]["count"] += row_count
        date_activities[date_str]["types"].add(row.activity_type)
        total_activities += row_count

    # Build response
    heatmap_days = []
    for date_str, data in date_activities.items():
        heatmap_days.append(
            ActivityHeatmapDay(
                date=datetime.fromisoformat(date_str).date(),
                count=data["count"],
                activity_types=list(data["types"]),
            )
        )

    return ActivityHeatmapResponse(
        days=heatmap_days,
        start_date=start_date,
        end_date=today,
        total_activities=total_activities,
    )
