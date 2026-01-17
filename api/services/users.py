"""User service for user-related business logic."""

from dataclasses import dataclass
from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncSession

from models import SubmissionType, User
from repositories.submission import SubmissionRepository
from repositories.user import UserRepository
from services.activity import (
    HeatmapData,
    StreakData,
    get_heatmap_data,
    get_streak_data,
)
from services.badges import compute_all_badges
from services.clerk import fetch_user_data
from services.hands_on_verification import get_requirement_by_id
from services.progress import fetch_user_progress, get_phase_completion_counts

StreakInfo = StreakData
HeatmapInfo = HeatmapData


def _is_placeholder_user(user_email: str) -> bool:
    """Check if user email indicates placeholder account.

    Placeholder accounts are created on first API access and later
    synced with Clerk data via webhooks.

    Args:
        user_email: User's email address

    Returns:
        True if email is a placeholder (not yet synced from Clerk)
    """
    return user_email.endswith("@placeholder.local")


def _needs_clerk_sync(user: User) -> bool:
    """Check if user needs data sync from Clerk.

    Users need sync if:
    - They have placeholder data
    - Missing avatar URL
    - Missing GitHub username

    Args:
        user: User ORM model

    Returns:
        True if user should be synced with Clerk
    """
    return (
        _is_placeholder_user(user.email)
        or not user.avatar_url
        or not user.github_username
    )


def _normalize_github_username(username: str | None) -> str | None:
    """Normalize GitHub username to lowercase for consistency.

    GitHub usernames are case-insensitive, so we normalize to lowercase
    to avoid duplicate accounts and enable case-insensitive lookups.

    Args:
        username: GitHub username (may be None)

    Returns:
        Normalized lowercase username or None
    """
    return username.lower() if username else None


@dataclass(frozen=True)
class UserData:
    """DTO for a user (service-layer return type)."""

    id: str
    email: str
    first_name: str | None
    last_name: str | None
    avatar_url: str | None
    github_username: str | None
    is_admin: bool
    created_at: datetime


def _to_user_data(user: User) -> UserData:
    return UserData(
        id=user.id,
        email=user.email,
        first_name=user.first_name,
        last_name=user.last_name,
        avatar_url=user.avatar_url,
        github_username=user.github_username,
        is_admin=user.is_admin,
        created_at=user.created_at,
    )


@dataclass
class PublicSubmissionInfo:
    """Public submission information for profile display."""

    requirement_id: str
    submission_type: str
    phase_id: int
    submitted_value: str
    name: str
    validated_at: object | None


@dataclass
class BadgeInfo:
    """Badge information."""

    id: str
    name: str
    description: str
    icon: str


@dataclass
class PublicProfileData:
    """Complete public profile data."""

    username: str | None
    first_name: str | None
    avatar_url: str | None
    current_phase: int
    phases_completed: int
    streak: StreakInfo
    activity_heatmap: HeatmapInfo
    member_since: datetime
    submissions: list[PublicSubmissionInfo]
    badges: list[BadgeInfo]


async def get_or_create_user(db: AsyncSession, user_id: str) -> UserData:
    """Get user from DB or create placeholder (will be synced via webhook).

    Uses repository pattern for database operations.
    Syncs missing data from Clerk if needed.
    """
    user_repo = UserRepository(db)
    user = await user_repo.get_or_create(user_id)

    if _needs_clerk_sync(user):
        clerk_data = await fetch_user_data(user_id)
        if clerk_data:
            is_placeholder = _is_placeholder_user(user.email)

            # Normalize GitHub username before passing to repository
            normalized_github_username = None
            if clerk_data.github_username and not user.github_username:
                normalized_github_username = _normalize_github_username(
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

    return _to_user_data(user)


async def get_public_profile(
    db: AsyncSession,
    username: str,
    viewer_user_id: str | None = None,
) -> PublicProfileData | None:
    """Build complete public profile data for a user.

    Returns None if user not found.
    """
    user_repo = UserRepository(db)
    submission_repo = SubmissionRepository(db)

    profile_user = await user_repo.get_by_github_username(username)
    if not profile_user:
        return None

    streak = await get_streak_data(db, profile_user.id)
    activity_heatmap = await get_heatmap_data(db, profile_user.id, days=270)

    db_submissions = await submission_repo.get_validated_by_user(profile_user.id)

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

    progress = await fetch_user_progress(db, profile_user.id)
    phase_completion_counts = get_phase_completion_counts(progress)

    earned_badges = compute_all_badges(
        phase_completion_counts=phase_completion_counts,
        longest_streak=streak.longest_streak,
    )
    badges = [
        BadgeInfo(
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
