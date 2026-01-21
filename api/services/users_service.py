"""User service for user-related business logic."""

import asyncio

from sqlalchemy.ext.asyncio import AsyncSession

from core.telemetry import log_metric, track_operation
from models import SubmissionType, User
from repositories.submission_repository import SubmissionRepository
from repositories.user_repository import UserRepository
from schemas import (
    BadgeData,
    PublicProfileData,
    PublicSubmissionInfo,
    UserResponse,
)
from services.activity_service import (
    get_heatmap_data,
    get_streak_data,
)
from services.badges_service import compute_all_badges
from services.clerk_service import fetch_user_data
from services.hands_on_verification_service import get_requirement_by_id
from services.progress_service import fetch_user_progress, get_phase_completion_counts


def _is_placeholder_user(user_email: str) -> bool:
    """Check if user email indicates placeholder account.

    Placeholder accounts are created on first API access and later
    synced with Clerk data via webhooks.
    """
    return user_email.endswith("@placeholder.local")


def _needs_clerk_sync(user: User) -> bool:
    """Check if user needs data sync from Clerk.

    Users need sync if:
    - They have placeholder data
    - Missing avatar URL
    - Missing GitHub username
    """
    return (
        _is_placeholder_user(user.email)
        or not user.avatar_url
        or not user.github_username
    )


def normalize_github_username(username: str | None) -> str | None:
    """Normalize GitHub username to lowercase for consistency.

    GitHub usernames are case-insensitive, so we normalize to lowercase
    to avoid duplicate accounts and enable case-insensitive lookups.
    """
    return username.lower() if username else None


def _to_user_response(user: User) -> UserResponse:
    return UserResponse(
        id=user.id,
        email=user.email,
        first_name=user.first_name,
        last_name=user.last_name,
        avatar_url=user.avatar_url,
        github_username=user.github_username,
        is_admin=user.is_admin,
        created_at=user.created_at,
    )


async def ensure_user_exists(db: AsyncSession, user_id: str) -> None:
    """Ensure user row exists in DB (for FK constraints). Fast path - no Clerk API call.

    Use this for endpoints that only need the user to exist but don't need profile data.
    The user will be created as a placeholder if they don't exist yet (handles race
    condition where API request arrives before Clerk webhook).

    For endpoints that need user profile data (email, name, avatar, is_admin),
    use get_or_create_user() instead.
    """
    user_repo = UserRepository(db)
    await user_repo.get_or_create(user_id)


@track_operation("user_get_or_create")
async def get_or_create_user(db: AsyncSession, user_id: str) -> UserResponse:
    """Get user from DB or create placeholder (will be synced via webhook).

    Uses repository pattern for database operations.
    Syncs missing data from Clerk if needed.
    """
    user_repo = UserRepository(db)
    user = await user_repo.get_or_create(user_id)

    if user.created_at == user.updated_at:
        log_metric("users.registered", 1)

    if _needs_clerk_sync(user):
        clerk_data = await fetch_user_data(user_id)
        if clerk_data:
            is_placeholder = _is_placeholder_user(user.email)

            normalized_github_username = None
            if clerk_data.github_username and not user.github_username:
                normalized_github_username = normalize_github_username(
                    clerk_data.github_username
                )

            await user_repo.update(
                user,
                email=clerk_data.email if clerk_data.email and is_placeholder else None,
                first_name=clerk_data.first_name
                if clerk_data.first_name and not user.first_name
                else None,
                last_name=clerk_data.last_name
                if clerk_data.last_name and not user.last_name
                else None,
                avatar_url=clerk_data.avatar_url
                if clerk_data.avatar_url and not user.avatar_url
                else None,
                github_username=normalized_github_username,
            )

    return _to_user_response(user)


async def get_public_profile(
    db: AsyncSession,
    username: str,
    viewer_user_id: str | None = None,
) -> PublicProfileData | None:
    """Build complete public profile data for a user.

    Returns None if user not found.
    Username lookup is case-insensitive (GitHub usernames are case-insensitive).
    """
    user_repo = UserRepository(db)
    submission_repo = SubmissionRepository(db)

    # Normalize username for case-insensitive lookup (GitHub usernames are case-insensitive)
    normalized_username = normalize_github_username(username)
    profile_user = await user_repo.get_by_github_username(normalized_username)
    if not profile_user:
        return None

    # TaskGroup cancels remaining tasks if one fails (safer than gather)
    async with asyncio.TaskGroup() as tg:
        streak_task = tg.create_task(get_streak_data(db, profile_user.id))
        heatmap_task = tg.create_task(get_heatmap_data(db, profile_user.id, days=270))
        submissions_task = tg.create_task(
            submission_repo.get_validated_by_user(profile_user.id)
        )
        progress_task = tg.create_task(fetch_user_progress(db, profile_user.id))

    streak = streak_task.result()
    activity_heatmap = heatmap_task.result()
    db_submissions = submissions_task.result()
    progress = progress_task.result()

    sensitive_submission_types = {
        SubmissionType.CTF_TOKEN,
        SubmissionType.DEPLOYED_APP,
        SubmissionType.CONTAINER_IMAGE,
        SubmissionType.API_CHALLENGE,
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
                validated_at=sub.validated_at,
            )
        )

    phase_completion_counts = get_phase_completion_counts(progress)

    earned_badges = compute_all_badges(
        phase_completion_counts=phase_completion_counts,
        longest_streak=streak.longest_streak,
        user_id=profile_user.id,
    )
    badges = [
        BadgeData(
            id=badge.id,
            name=badge.name,
            description=badge.description,
            icon=badge.icon,
        )
        for badge in earned_badges
    ]

    phases_completed = progress.phases_completed
    current_phase = progress.current_phase

    profile_data = PublicProfileData(
        username=profile_user.github_username,
        first_name=profile_user.first_name,
        avatar_url=profile_user.avatar_url,
        current_phase=current_phase,
        phases_completed=phases_completed,
        streak=streak,
        activity_heatmap=activity_heatmap,
        member_since=profile_user.created_at,
        submissions=submissions,
        badges=badges,
    )

    return profile_data
