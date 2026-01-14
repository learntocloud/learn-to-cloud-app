"""User-related endpoints."""

from fastapi import APIRouter, HTTPException

from core.auth import OptionalUserId, UserId
from core.database import DbSession
from schemas import (
    ActivityHeatmapDay,
    ActivityHeatmapResponse,
    BadgeResponse,
    PublicProfileResponse,
    PublicSubmission,
    StreakResponse,
    UserResponse,
)
from services.users import get_or_create_user, get_public_profile

__all__ = ["router", "get_or_create_user"]

router = APIRouter(prefix="/api/user", tags=["users"])

@router.get("/me", response_model=UserResponse)
async def get_current_user(user_id: UserId, db: DbSession) -> UserResponse:
    """Get current user info."""
    user = await get_or_create_user(db, user_id)
    return UserResponse.model_validate(user)

@router.get("/profile/{username}", response_model=PublicProfileResponse)
async def get_public_profile_endpoint(
    username: str,
    db: DbSession,
    user_id: OptionalUserId = None,
) -> PublicProfileResponse:
    """Get a user's public profile by username (GitHub username)."""
    result = await get_public_profile(db, username, user_id)

    if result is None:
        raise HTTPException(status_code=404, detail="User not found")

    _, profile_data = result

    streak = StreakResponse.model_validate(profile_data.streak)

    heatmap_days = [ActivityHeatmapDay.model_validate(day) for day in profile_data.activity_heatmap.days]
    activity_heatmap = ActivityHeatmapResponse(
        days=heatmap_days,
        start_date=profile_data.activity_heatmap.start_date,
        end_date=profile_data.activity_heatmap.end_date,
        total_activities=profile_data.activity_heatmap.total_activities,
    )

    submissions = [PublicSubmission.model_validate(sub) for sub in profile_data.submissions]
    badges = [BadgeResponse.model_validate(badge) for badge in profile_data.badges]

    return PublicProfileResponse(
        username=profile_data.username,
        first_name=profile_data.first_name,
        avatar_url=profile_data.avatar_url,
        current_phase=profile_data.current_phase,
        phases_completed=profile_data.phases_completed,
        streak=streak,
        activity_heatmap=activity_heatmap,
        member_since=profile_data.member_since,
        submissions=submissions,
        badges=badges,
    )
