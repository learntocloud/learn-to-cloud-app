"""User-related endpoints."""

from fastapi import APIRouter, HTTPException, Request

from core.auth import OptionalUserId, UserId
from core.database import DbSession, DbSessionReadOnly
from core.ratelimit import limiter
from schemas import (
    BadgeCatalogResponse,
    PublicProfileData,
    UserResponse,
)
from services.badges_service import get_badge_catalog
from services.users_service import (
    UserNotFoundError,
    delete_user_account,
    get_or_create_user,
    get_public_profile,
)

__all__ = ["router"]

router = APIRouter(prefix="/api/user", tags=["users"])


@router.get(
    "/me",
    response_model=UserResponse,
    summary="Get current user",
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
    response_model=PublicProfileData,
    summary="Get public user profile",
    responses={404: {"description": "User not found"}},
)
@limiter.limit("30/minute")
async def get_public_profile_endpoint(
    request: Request,
    username: str,
    db: DbSessionReadOnly,
    user_id: OptionalUserId = None,
) -> PublicProfileData:
    """Get a user's public profile by username (GitHub username)."""
    result = await get_public_profile(db, username, user_id)

    if result is None:
        raise HTTPException(status_code=404, detail="User not found")

    return result


@router.get(
    "/badges/catalog",
    response_model=BadgeCatalogResponse,
    summary="Get badge catalog",
    responses={200: {"description": "Badge catalog"}},
)
@limiter.limit("30/minute")
async def get_badge_catalog_endpoint(request: Request) -> BadgeCatalogResponse:
    """Get the badge catalog for public display."""
    phase_badges, total_badges = get_badge_catalog()
    return BadgeCatalogResponse(
        phase_badges=phase_badges,
        total_badges=total_badges,
    )


@router.delete(
    "/me",
    status_code=204,
    summary="Delete current user account",
    responses={
        204: {"description": "Account deleted"},
        401: {"description": "Not authenticated"},
        404: {"description": "User not found"},
    },
)
@limiter.limit("3/hour")
async def delete_current_user(request: Request, user_id: UserId, db: DbSession) -> None:
    """Permanently delete the authenticated user's account and all associated data."""
    try:
        await delete_user_account(db, user_id)
    except UserNotFoundError:
        raise HTTPException(status_code=404, detail="User not found")

    request.session.clear()
