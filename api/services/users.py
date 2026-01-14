"""User service for user-related business logic."""

from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession

from models import User
from repositories.submission import SubmissionRepository
from repositories.user import UserRepository
from services.activity import (
    HeatmapData,
    HeatmapDay,
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
    member_since: object
    submissions: list[PublicSubmissionInfo]
    badges: list[BadgeInfo]

async def get_or_create_user(db: AsyncSession, user_id: str) -> User:
    """Get user from DB or create placeholder (will be synced via webhook).

    Uses repository pattern for database operations.
    Syncs missing data from Clerk if needed.
    """
    user_repo = UserRepository(db)
    user = await user_repo.get_or_create(user_id)

    if user_repo.needs_sync(user):
        clerk_data = await fetch_user_data(user_id)
        if clerk_data:
            is_placeholder = user_repo.is_placeholder(user)
            await user_repo.update(
                user,
                email=clerk_data.email if clerk_data.email and is_placeholder else None,
                first_name=clerk_data.first_name if clerk_data.first_name and not user.first_name else None,
                last_name=clerk_data.last_name if clerk_data.last_name and not user.last_name else None,
                avatar_url=clerk_data.avatar_url if clerk_data.avatar_url and not user.avatar_url else None,
                github_username=clerk_data.github_username if clerk_data.github_username and not user.github_username else None,
            )

    return user

async def get_public_profile(
    db: AsyncSession,
    username: str,
    viewer_user_id: str | None = None,
) -> tuple[User, PublicProfileData] | None:
    """Build complete public profile data for a user.

    Returns None if user not found.
    Raises PermissionError if profile is private and viewer is not owner.
    """
    user_repo = UserRepository(db)
    submission_repo = SubmissionRepository(db)

    profile_user = await user_repo.get_by_github_username(username)
    if not profile_user:
        return None

    is_owner = viewer_user_id == profile_user.id if viewer_user_id else False
    if not is_owner and not profile_user.is_profile_public:
        raise PermissionError("This profile is private")

    streak = await get_streak_data(db, profile_user.id)
    activity_heatmap = await get_heatmap_data(db, profile_user.id, days=270)

    db_submissions = await submission_repo.get_validated_by_user(profile_user.id)

    submissions = []
    for sub in db_submissions:
        requirement = get_requirement_by_id(sub.requirement_id)
        submissions.append(
            PublicSubmissionInfo(
                requirement_id=sub.requirement_id,
                submission_type=sub.submission_type.value if hasattr(sub.submission_type, 'value') else str(sub.submission_type),
                phase_id=sub.phase_id,
                submitted_value=sub.submitted_value,
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

    return profile_user, profile_data
