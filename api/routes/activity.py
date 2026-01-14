"""Activity tracking and streak calculation endpoints."""

import logging

from fastapi import APIRouter

from core.auth import UserId
from core.database import DbSession
from schemas import (
    ActivityHeatmapDay,
    ActivityHeatmapResponse,
    ActivityLogRequest,
    ActivityResponse,
    StreakResponse,
)
from services.activity import get_heatmap_data, get_streak_data, log_activity

from services.users import get_or_create_user

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/activity", tags=["activity"])

@router.post("/log", response_model=ActivityResponse)
async def log_activity_endpoint(
    activity: ActivityLogRequest,
    user_id: UserId,
    db: DbSession,
) -> ActivityResponse:
    """Manually log a user activity.

    Note: Most activities are logged automatically by other endpoints
    (question attempts, topic completions, certificates).
    """
    await get_or_create_user(db, user_id)

    result = await log_activity(
        db=db,
        user_id=user_id,
        activity_type=activity.activity_type,
        reference_id=activity.reference_id,
    )

    return ActivityResponse(
        id=result.id,
        activity_type=result.activity_type,
        activity_date=result.activity_date,
        reference_id=result.reference_id,
        created_at=result.created_at,
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

    streak_data = await get_streak_data(db, user_id)

    return StreakResponse.model_validate(streak_data)

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

    heatmap = await get_heatmap_data(db, user_id, days)

    heatmap_days = [ActivityHeatmapDay.model_validate(day) for day in heatmap.days]

    return ActivityHeatmapResponse(
        days=heatmap_days,
        start_date=heatmap.start_date,
        end_date=heatmap.end_date,
        total_activities=heatmap.total_activities,
    )
