"""User-related endpoints."""

from fastapi import APIRouter, HTTPException, Request

from core.auth import OptionalUserId, UserId
from core.database import DbSession, DbSessionReadOnly
from core.ratelimit import limiter
from schemas import (
    BadgeCatalogResponse,
    BadgeResponse,
    PublicProfileResponse,
    PublicSubmission,
    UserResponse,
)
from services.badges_service import get_badge_catalog
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
    db: DbSessionReadOnly,
    user_id: OptionalUserId = None,
) -> PublicProfileResponse:
    """Get a user's public profile by username (GitHub username)."""
    result = await get_public_profile(db, username, user_id)

    if result is None:
        raise HTTPException(status_code=404, detail="User not found")

    profile_data = result

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
        member_since=profile_data.member_since,
        submissions=submissions,
        badges=badges,
    )


@router.get(
    "/badges/catalog",
    response_model=BadgeCatalogResponse,
    summary="Get badge catalog",
    responses={200: {"description": "Badge catalog"}},
)
@limiter.limit("30/minute")
async def get_badge_catalog_endpoint(request: Request) -> BadgeCatalogResponse:
    """Get the badge catalog for public display."""
    phase_badges, total_badges, phase_themes = get_badge_catalog()
    return BadgeCatalogResponse(
        phase_badges=phase_badges,
        total_badges=total_badges,
        phase_themes=phase_themes,
    )
