"""User-related endpoints and helpers."""

import logging
from datetime import datetime, timezone


import httpx
from fastapi import APIRouter
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from shared import (
    get_settings,
    DbSession,
    UserId,
    User,
    UserResponse,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/user", tags=["users"])

# Reusable HTTP client for Clerk API calls (connection pooling)
_http_client: httpx.AsyncClient | None = None


async def get_http_client() -> httpx.AsyncClient:
    """Get or create a reusable HTTP client with connection pooling."""
    global _http_client
    if _http_client is None or _http_client.is_closed:
        _http_client = httpx.AsyncClient(
            timeout=10.0,
            limits=httpx.Limits(max_connections=20, max_keepalive_connections=10),
        )
    return _http_client


# ============ Helper Functions ============

async def fetch_github_username_from_clerk(user_id: str) -> str | None:
    """
    Fetch GitHub username directly from Clerk API.
    This is used when the user doesn't have a github_username stored.
    """
    settings = get_settings()
    if not settings.clerk_secret_key:
        return None

    try:
        client = await get_http_client()
        response = await client.get(
            f"https://api.clerk.com/v1/users/{user_id}",
            headers={
                "Authorization": f"Bearer {settings.clerk_secret_key}",
                "Content-Type": "application/json",
            },
        )

        if response.status_code != 200:
            logger.warning(f"Failed to fetch user from Clerk: {response.status_code}")
            return None

        data = response.json()

        # Check external_accounts for GitHub
        external_accounts = data.get("external_accounts", [])
        for account in external_accounts:
            provider = account.get("provider", "")
            # Clerk uses "oauth_github" as the provider name
            if "github" in provider.lower():
                username = account.get("username")
                if username:
                    return username

        return None
    except Exception as e:
        logger.warning(f"Error fetching GitHub username from Clerk: {e}")
        return None


async def get_or_create_user(db: AsyncSession, user_id: str) -> User:
    """Get user from DB or create placeholder (will be synced via webhook).
    
    Note: Does not commit - relies on the get_db dependency to handle transactions.
    """
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()

    if not user:
        user = User(id=user_id, email=f"{user_id}@placeholder.local")
        db.add(user)
        await db.flush()  # Flush to get the user in session without committing

    # If user doesn't have github_username, try to fetch it from Clerk
    if not user.github_username:
        github_username = await fetch_github_username_from_clerk(user_id)
        if github_username:
            user.github_username = github_username
            user.updated_at = datetime.now(timezone.utc)
            # No need to flush here - changes tracked automatically

    return user


# ============ Routes ============

@router.get("/me", response_model=UserResponse)
async def get_current_user(user_id: UserId, db: DbSession) -> UserResponse:
    """Get current user info."""
    user = await get_or_create_user(db, user_id)
    return UserResponse.model_validate(user)
