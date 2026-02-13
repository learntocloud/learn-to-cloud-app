"""User service for user-related business logic."""

import logging

from sqlalchemy.ext.asyncio import AsyncSession

from models import SubmissionType, User
from repositories.submission_repository import SubmissionRepository
from repositories.user_repository import UserRepository
from schemas import (
    PublicProfileData,
    PublicSubmissionInfo,
    UserResponse,
)
from services.badges_service import compute_all_badges
from services.hands_on_verification_service import get_requirement_by_id
from services.progress_service import fetch_user_progress, get_phase_completion_counts

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


def _to_user_response(user: User) -> UserResponse:
    return UserResponse(
        id=user.id,
        first_name=user.first_name,
        last_name=user.last_name,
        avatar_url=user.avatar_url,
        github_username=user.github_username,
        is_admin=user.is_admin,
        created_at=user.created_at,
    )


async def get_user_by_id(db: AsyncSession, user_id: int) -> User | None:
    """Get a user by ID, or None if not found."""
    user_repo = UserRepository(db)
    return await user_repo.get_by_id(user_id)


async def ensure_user_exists(db: AsyncSession, user_id: int) -> None:
    """Ensure user row exists in DB (for FK constraints). Fast path.

    Use this for endpoints that only need the user to exist but don't need profile data.
    """
    user_repo = UserRepository(db)
    await user_repo.get_or_create(user_id)


async def get_or_create_user(db: AsyncSession, user_id: int) -> UserResponse:
    """Get user from DB. User must already exist (created during OAuth callback)."""
    user_repo = UserRepository(db)
    user = await user_repo.get_by_id(user_id)
    if user is None:
        # This shouldn't happen in normal flow - user is created during OAuth callback
        user = await user_repo.get_or_create(user_id)

    return _to_user_response(user)


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


async def get_public_profile(
    db: AsyncSession,
    username: str,
    viewer_user_id: int | None = None,
) -> PublicProfileData | None:
    """Build complete public profile data for a user.

    Returns None if user not found.
    Username lookup is case-insensitive (GitHub usernames are case-insensitive).
    """
    user_repo = UserRepository(db)
    submission_repo = SubmissionRepository(db)

    # Normalize username (GitHub usernames are case-insensitive)
    normalized_username = normalize_github_username(username)
    if not normalized_username:
        return None
    profile_user = await user_repo.get_by_github_username(normalized_username)
    if not profile_user:
        return None

    # Run sequentially - asyncpg connections are NOT safe for concurrent use
    # on the same AsyncSession. Using TaskGroup/gather here caused intermittent
    # InterfaceError on cache-miss when both queries hit the DB.
    db_submissions = await submission_repo.get_validated_by_user(profile_user.id)
    progress = await fetch_user_progress(db, profile_user.id)

    sensitive_submission_types = {
        SubmissionType.CTF_TOKEN,
        SubmissionType.IAC_TOKEN,
    }

    submissions = []
    for sub in db_submissions:
        requirement = get_requirement_by_id(sub.requirement_id)
        submitted_value = (
            "[redacted]"
            if sub.submission_type in sensitive_submission_types
            else sub.submitted_value
        )
        submissions.append(
            PublicSubmissionInfo(
                requirement_id=sub.requirement_id,
                submission_type=sub.submission_type.value
                if hasattr(sub.submission_type, "value")
                else str(sub.submission_type),
                phase_id=sub.phase_id,
                submitted_value=submitted_value,
                name=requirement.name if requirement else sub.requirement_id,
                description=requirement.description if requirement else None,
                validated_at=sub.validated_at,
            )
        )

    phase_completion_counts = get_phase_completion_counts(progress)

    earned_badges = compute_all_badges(
        phase_completion_counts=phase_completion_counts,
        user_id=profile_user.id,
    )

    phases_completed = progress.phases_completed
    current_phase = progress.current_phase

    profile_data = PublicProfileData(
        username=profile_user.github_username,
        first_name=profile_user.first_name,
        avatar_url=profile_user.avatar_url,
        current_phase=current_phase,
        phases_completed=phases_completed,
        submissions=submissions,
        badges=earned_badges,
    )

    return profile_data


class UserNotFoundError(Exception):
    """Raised when a user is not found in the database."""

    def __init__(self, user_id: int) -> None:
        self.user_id = user_id
        super().__init__(f"User not found: {user_id}")


async def delete_user_account(db: AsyncSession, user_id: int) -> None:
    """Permanently delete a user and all associated data.

    Cascades to submissions, certificates, and step progress.

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
