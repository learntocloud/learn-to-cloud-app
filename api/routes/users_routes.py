"""User-related endpoints."""

from fastapi import APIRouter, HTTPException, Request

from core.auth import OptionalUserId, UserId
from core.database import DbSession
from core.ratelimit import limiter
from models import ActivityType
from schemas import (
    ActivityHeatmapDay,
    ActivityHeatmapResponse,
    BadgeResponse,
    PublicProfileResponse,
    PublicSubmission,
    StreakResponse,
    UserResponse,
)
from services.users_service import get_or_create_user, get_public_profile

__all__ = ["router", "get_or_create_user"]

router = APIRouter(prefix="/api/user", tags=["users"])


@router.get(
    "/me",
    response_model=UserResponse,
    responses={401: {"description": "Not authenticated"}},
)
@limiter.limit("30/minute")
async def get_current_user(
    request: Request, user_id: UserId, db: DbSession
) -> UserResponse:
    """Get current user info."""
    user = await get_or_create_user(db, user_id)
    return UserResponse.model_validate(user)


@router.get(
    "/profile/{username}",
    response_model=PublicProfileResponse,
    responses={404: {"description": "User not found"}},
)
@limiter.limit("30/minute")
async def get_public_profile_endpoint(
    request: Request,
    username: str,
    db: DbSession,
    user_id: OptionalUserId = None,
) -> PublicProfileResponse:
    """Get a user's public profile by username (GitHub username)."""
    result = await get_public_profile(db, username, user_id)

    if result is None:
        raise HTTPException(status_code=404, detail="User not found")

    profile_data = result

    # Service returns StreakData which is compatible with StreakResponse
    streak = StreakResponse.model_validate(profile_data.streak.model_dump())

    # Transform HeatmapDay (string types) to ActivityHeatmapDay (enum types)
    heatmap_days = [
        ActivityHeatmapDay(
            date=day.date,
            count=day.count,
            activity_types=[ActivityType(t) for t in day.activity_types],
        )
        for day in profile_data.activity_heatmap.days
    ]
    activity_heatmap = ActivityHeatmapResponse(
        days=heatmap_days,
        start_date=profile_data.activity_heatmap.start_date,
        end_date=profile_data.activity_heatmap.end_date,
        total_activities=profile_data.activity_heatmap.total_activities,
    )

    # Service returns Pydantic models, convert with model_dump
    submissions = [
        PublicSubmission.model_validate(sub.model_dump())
        for sub in profile_data.submissions
    ]
    badges = [
        BadgeResponse.model_validate(badge.model_dump())
        for badge in profile_data.badges
    ]

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
