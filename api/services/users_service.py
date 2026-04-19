"""User service for user-related business logic."""

import logging

from sqlalchemy.ext.asyncio import AsyncSession

from models import User
from repositories.user_repository import UserRepository

logger = logging.getLogger(__name__)


def normalize_github_username(username: str | None) -> str | None:
    """Normalize GitHub username to lowercase for consistency.

    GitHub usernames are case-insensitive, so we normalize to lowercase
    to avoid duplicate accounts and enable case-insensitive lookups.
    """
    return username.lower() if username else None


def parse_display_name(name: str | None) -> tuple[str, str]:
    """Split a display name into (first_name, last_name).

    Handles single names, multi-part names, and empty/None values.
    """
    if not name:
        return ("", "")
    parts = name.split(" ", 1)
    return (parts[0], parts[1] if len(parts) > 1 else "")


async def get_user_by_id(db: AsyncSession, user_id: int) -> User | None:
    """Get a user by ID, or None if not found."""
    user_repo = UserRepository(db)
    return await user_repo.get_by_id(user_id)


async def get_or_create_user_from_github(
    db: AsyncSession,
    *,
    github_id: int,
    first_name: str,
    last_name: str,
    avatar_url: str | None,
    github_username: str,
) -> User:
    """Create or update a user from GitHub OAuth profile data.

    Called during the OAuth callback. Uses upsert to handle both new
    and returning users in a single query.

    If another user already has this GitHub username, it is cleared from
    them first (GitHub usernames are unique across our user base).
    """
    user_repo = UserRepository(db)
    normalized_username = normalize_github_username(github_username)

    # Clear username from any other user before upsert (business rule:
    # GitHub usernames must be unique, latest OAuth login wins).
    if normalized_username:
        existing_owner = await user_repo.get_by_github_username(normalized_username)
        if existing_owner and existing_owner.id != github_id:
            await user_repo.clear_github_username(existing_owner.id)

    user = await user_repo.upsert(
        github_id,
        first_name=first_name,
        last_name=last_name,
        avatar_url=avatar_url,
        github_username=normalized_username,
    )

    logger.info(
        "user.upserted",
        extra={"user_id": github_id, "github_username": normalized_username},
    )

    return user


class UserNotFoundError(Exception):
    """Raised when a user is not found in the database."""

    def __init__(self, user_id: int) -> None:
        self.user_id = user_id
        super().__init__(f"User not found: {user_id}")


async def delete_user_account(db: AsyncSession, user_id: int) -> None:
    """Permanently delete a user and all associated data.

    Cascades to submissions and step progress.

    Raises:
        UserNotFoundError: If the user does not exist.
    """
    user_repo = UserRepository(db)
    user = await user_repo.get_by_id(user_id)
    if user is None:
        raise UserNotFoundError(user_id)

    github_username = user.github_username
    await user_repo.delete(user_id)

    logger.info(
        "user.account_deleted",
        extra={"user_id": user_id, "github_username": github_username},
    )
