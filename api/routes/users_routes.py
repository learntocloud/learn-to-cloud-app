"""User-related endpoints."""

from fastapi import APIRouter, HTTPException, Request

from core.auth import UserId
from core.database import DbSession
from core.ratelimit import limiter
from schemas import UserResponse
from services.users_service import (
    UserNotFoundError,
    delete_user_account,
    get_or_create_user,
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
