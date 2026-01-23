"""Activity tracking and streak calculation endpoints."""

from fastapi import APIRouter, Request

from core import get_logger
from core.auth import UserId
from core.database import DbSession
from core.ratelimit import limiter
from core.wide_event import set_wide_event_fields
from schemas import (
    StreakResponse,
)
from services.activity_service import get_streak_data
from services.users_service import ensure_user_exists

logger = get_logger(__name__)

router = APIRouter(prefix="/api/activity", tags=["activity"])


@router.get(
    "/streak",
    response_model=StreakResponse,
    responses={401: {"description": "Not authenticated"}},
)
@limiter.limit("60/minute")
async def get_user_streak(
    request: Request,
    user_id: UserId,
    db: DbSession,
) -> StreakResponse:
    """Get the user's current streak information.

    Streak calculation allows up to 2 skipped days per week.
    """
    await ensure_user_exists(db, user_id)

    streak_data = await get_streak_data(db, user_id)

    set_wide_event_fields(current_streak=streak_data.current_streak)

    return StreakResponse.model_validate(streak_data)
