"""Activity tracking and streak calculation endpoints."""

import logging

from fastapi import APIRouter

from core.auth import UserId
from core.database import DbSession
from schemas import (
    StreakResponse,
)
from services.activity import get_streak_data
from services.users import get_or_create_user

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/activity", tags=["activity"])


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
