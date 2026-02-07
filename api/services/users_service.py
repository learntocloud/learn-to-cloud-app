"""User service for user-related business logic."""

from sqlalchemy.ext.asyncio import AsyncSession

from core.telemetry import log_business_event, track_operation
from core.wide_event import set_wide_event_fields
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


def normalize_github_username(username: str | None) -> str | None:
    """Normalize GitHub username to lowercase for consistency.

    GitHub usernames are case-insensitive, so we normalize to lowercase
    to avoid duplicate accounts and enable case-insensitive lookups.
    """
    return username.lower() if username else None


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


@track_operation("user_get_or_create")
async def get_or_create_user(db: AsyncSession, user_id: int) -> UserResponse:
    """Get user from DB. User must already exist (created during OAuth callback)."""
    user_repo = UserRepository(db)
    user = await user_repo.get_by_id(user_id)
    if user is None:
        # This shouldn't happen in normal flow - user is created during OAuth callback
        user = await user_repo.get_or_create(user_id)

    return _to_user_response(user)


@track_operation("user_get_or_create_from_github")
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
    """
    user_repo = UserRepository(db)

    user = await user_repo.upsert(
        github_id,
        first_name=first_name,
        last_name=last_name,
        avatar_url=avatar_url,
        github_username=normalize_github_username(github_username),
    )
    await db.commit()

    is_new_user = user.created_at == user.updated_at
    if is_new_user:
        log_business_event("users.registered", 1)
        set_wide_event_fields(user_is_new=True)

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
        member_since=profile_user.created_at,
        submissions=submissions,
        badges=earned_badges,
    )

    set_wide_event_fields(
        profile_viewed_user_id=profile_user.id,
        profile_viewed_username=profile_user.github_username,
        profile_phases_completed=phases_completed,
        profile_badges_count=len(earned_badges),
    )

    return profile_data
