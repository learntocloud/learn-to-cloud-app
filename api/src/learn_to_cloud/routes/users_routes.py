"""User-related endpoints."""

from fastapi import APIRouter, Request
from learn_to_cloud_shared.schemas import UserResponse

from learn_to_cloud.core.auth import CurrentAccount, CurrentUser
from learn_to_cloud.services.sessions_service import mutate_account

__all__ = ["router"]

router = APIRouter(prefix="/api/user", tags=["users"])


@router.get(
    "/me",
    summary="Get current user",
    responses={401: {"description": "Not authenticated"}},
)
async def get_current_user(account: CurrentAccount) -> UserResponse:
    """Get current user info."""
    return UserResponse.model_validate(account)


@router.delete(
    "/me",
    status_code=204,
    summary="Delete current user account",
    responses={
        204: {"description": "Account deleted"},
        401: {"description": "Not authenticated"},
    },
)
async def delete_current_user(request: Request, current_user: CurrentUser) -> None:
    """Permanently delete the authenticated user's account and all associated data."""
    await mutate_account(request, current_user.user_id, delete_account=True)
