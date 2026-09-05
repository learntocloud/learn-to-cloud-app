"""User service for user-related business logic."""

import logging

from learn_to_cloud_shared.models import User
from learn_to_cloud_shared.repositories.user_repository import UserRepository
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)


def normalize_github_username(username: str | None) -> str | None:
    """Return the lowercase username, or None if it is missing or empty."""
    return username.lower() if username else None


def normalize_display_name(name: object) -> str | None:
    """Preserve nonblank provider names that PostgreSQL can store."""
    if name is None:
        return None
    if isinstance(name, str):
        if not name.strip():
            return None
        if "\x00" not in name:
            try:
                name.encode("utf-8")
            except UnicodeEncodeError:
                logger.warning("auth.callback.display_name_ignored")
                return None
            return name
    logger.warning("auth.callback.display_name_ignored")
    return None


async def get_or_create_user_from_github(
    db: AsyncSession,
    *,
    github_id: int,
    display_name: object,
    avatar_url: str | None,
    github_username: str,
) -> User:
    """Create or update a user from GitHub OAuth profile data.

    Called during the OAuth callback. Identity is the immutable GitHub
    numeric ID (``github_id``), so the upsert keys on it. ``github_username``
    is display-only and refreshed from GitHub on every login.
    """
    user_repo = UserRepository(db)
    normalized_username = normalize_github_username(github_username)
    if not normalized_username:
        raise ValueError("github_username is required and cannot be empty")

    user = await user_repo.upsert(
        github_id,
        display_name=normalize_display_name(display_name),
        avatar_url=avatar_url,
        github_username=normalized_username,
    )
    return user
