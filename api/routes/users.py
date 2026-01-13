"""User-related endpoints and helpers."""

import logging
import time
from datetime import UTC, datetime

import httpx
from fastapi import APIRouter, HTTPException
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from shared.auth import OptionalUserId, UserId
from shared.badges import compute_all_badges
from shared.config import get_settings
from shared.database import DbSession
from shared.github import get_requirement_by_id
from shared.models import (
    ChecklistProgress,
    GitHubSubmission,
    QuestionAttempt,
    User,
    UserActivity,
)
from shared.schemas import (
    ActivityHeatmapDay,
    ActivityHeatmapResponse,
    BadgeResponse,
    PublicProfileResponse,
    PublicSubmission,
    StreakResponse,
    UserResponse,
)
from shared.streaks import MAX_SKIP_DAYS, calculate_streak_with_forgiveness

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/user", tags=["users"])

# Reusable HTTP client for Clerk API calls (connection pooling)
_http_client: httpx.AsyncClient | None = None

# Simple in-process backoff to avoid hammering Clerk on repeated failures.
# Keyed by Clerk user_id, value is next-allowed UNIX timestamp.
_clerk_lookup_backoff_until: dict[str, float] = {}
_CLERK_LOOKUP_BACKOFF_SECONDS = 300.0


def _cleanup_expired_backoffs() -> None:
    """Remove expired backoff entries to prevent unbounded memory growth."""
    now = time.time()
    expired = [k for k, v in _clerk_lookup_backoff_until.items() if v <= now]
    for k in expired:
        del _clerk_lookup_backoff_until[k]


async def get_http_client() -> httpx.AsyncClient:
    """Get or create a reusable HTTP client with connection pooling."""
    global _http_client
    if _http_client is None or _http_client.is_closed:
        settings = get_settings()
        _http_client = httpx.AsyncClient(
            timeout=settings.http_timeout,
            limits=httpx.Limits(max_connections=20, max_keepalive_connections=10),
        )
    return _http_client


async def close_http_client() -> None:
    """Close the reusable HTTP client (called on application shutdown)."""
    global _http_client
    if _http_client is None:
        return
    if not _http_client.is_closed:
        await _http_client.aclose()
    _http_client = None


# ============ Helper Functions ============


class ClerkUserData:
    """Data fetched from Clerk API for a user."""

    def __init__(
        self,
        *,
        email: str | None = None,
        first_name: str | None = None,
        last_name: str | None = None,
        avatar_url: str | None = None,
        github_username: str | None = None,
    ):
        self.email = email
        self.first_name = first_name
        self.last_name = last_name
        self.avatar_url = avatar_url
        self.github_username = github_username


async def fetch_user_data_from_clerk(user_id: str) -> ClerkUserData | None:
    """
    Fetch full user data from Clerk API.
    This is used when the user doesn't have complete profile data stored.
    Returns avatar_url (which comes from GitHub if using GitHub OAuth),
    name, email, and github_username.
    """
    settings = get_settings()
    if not settings.clerk_secret_key:
        return None

    _cleanup_expired_backoffs()

    now = time.time()
    backoff_until = _clerk_lookup_backoff_until.get(user_id)
    if backoff_until is not None and backoff_until > now:
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

        # Extract primary email
        email_addresses = data.get("email_addresses", [])
        primary_email = next(
            (
                e.get("email_address")
                for e in email_addresses
                if e.get("id") == data.get("primary_email_address_id")
            ),
            email_addresses[0].get("email_address") if email_addresses else None,
        )

        # Extract GitHub username from external_accounts
        github_username = None
        external_accounts = data.get("external_accounts", [])
        for account in external_accounts:
            provider = account.get("provider", "")
            # Clerk uses "oauth_github" as the provider name
            if "github" in provider.lower():
                github_username = account.get("username")
                break

        return ClerkUserData(
            email=primary_email,
            first_name=data.get("first_name"),
            last_name=data.get("last_name"),
            avatar_url=data.get(
                "image_url"
            ),  # Clerk's image_url includes GitHub avatar
            github_username=github_username,
        )
    except Exception as e:
        _clerk_lookup_backoff_until[user_id] = (
            time.time() + _CLERK_LOOKUP_BACKOFF_SECONDS
        )
        logger.warning(f"Error fetching user data from Clerk: {e}")
        return None


async def fetch_github_username_from_clerk(user_id: str) -> str | None:
    """
    Fetch GitHub username directly from Clerk API.
    This is used when the user doesn't have a github_username stored.
    """
    clerk_data = await fetch_user_data_from_clerk(user_id)
    return clerk_data.github_username if clerk_data else None


async def get_or_create_user(db: AsyncSession, user_id: str) -> User:
    """Get user from DB or create placeholder (will be synced via webhook).

    Uses INSERT ... ON CONFLICT to handle concurrent requests safely.
    Note: Does not commit - relies on the get_db dependency to handle transactions.
    """
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()

    if not user:
        # Use upsert to handle race condition where another request
        # creates the same user between our SELECT and INSERT
        bind = db.get_bind()
        dialect = bind.dialect.name if bind else ""

        if dialect == "postgresql":
            from sqlalchemy.dialects.postgresql import insert as pg_insert

            stmt = (
                pg_insert(User)
                .values(
                    id=user_id,
                    email=f"{user_id}@placeholder.local",
                )
                .on_conflict_do_nothing(index_elements=["id"])
            )
            await db.execute(stmt)
        elif dialect == "sqlite":
            from sqlalchemy.dialects.sqlite import insert as sqlite_insert

            stmt = (
                sqlite_insert(User)
                .values(
                    id=user_id,
                    email=f"{user_id}@placeholder.local",
                )
                .on_conflict_do_nothing(index_elements=["id"])
            )
            await db.execute(stmt)
        else:
            # Fallback: catch integrity error
            try:
                user = User(id=user_id, email=f"{user_id}@placeholder.local")
                db.add(user)
                await db.flush()
            except IntegrityError:
                await db.rollback()

        # Re-fetch the user (either we inserted it or another request did)
        result = await db.execute(select(User).where(User.id == user_id))
        user = result.scalar_one()

    # Check if user has placeholder/missing data and needs sync from Clerk
    is_placeholder = user.email.endswith("@placeholder.local")
    needs_sync = is_placeholder or not user.avatar_url or not user.github_username

    if needs_sync:
        clerk_data = await fetch_user_data_from_clerk(user_id)
        if clerk_data:
            updated = False
            if clerk_data.email and is_placeholder:
                user.email = clerk_data.email
                updated = True
            if clerk_data.first_name and not user.first_name:
                user.first_name = clerk_data.first_name
                updated = True
            if clerk_data.last_name and not user.last_name:
                user.last_name = clerk_data.last_name
                updated = True
            if clerk_data.avatar_url and not user.avatar_url:
                user.avatar_url = clerk_data.avatar_url
                updated = True
            if clerk_data.github_username and not user.github_username:
                user.github_username = clerk_data.github_username
                updated = True
            if updated:
                user.updated_at = datetime.now(UTC)
                # No need to flush - changes tracked automatically

    return user


# ============ Routes ============


@router.get("/me", response_model=UserResponse)
async def get_current_user(user_id: UserId, db: DbSession) -> UserResponse:
    """Get current user info."""
    user = await get_or_create_user(db, user_id)
    return UserResponse.model_validate(user)


@router.get("/profile/{username}", response_model=PublicProfileResponse)
async def get_public_profile(
    username: str,
    db: DbSession,
    user_id: OptionalUserId = None,
) -> PublicProfileResponse:
    """Get a user's public profile by username (GitHub username).

    If the viewing user is the profile owner, always show the profile.
    Otherwise, check if the profile is public.
    """
    # Find user by GitHub username
    result = await db.execute(select(User).where(User.github_username == username))
    profile_user = result.scalar_one_or_none()

    if not profile_user:
        raise HTTPException(status_code=404, detail="User not found")

    # Check if profile is public (or if viewer is the owner)
    is_owner = user_id == profile_user.id if user_id else False
    if not is_owner and not profile_user.is_profile_public:
        raise HTTPException(status_code=403, detail="This profile is private")

    # Get completed checklist items count
    checklist_result = await db.execute(
        select(func.count(ChecklistProgress.id)).where(
            ChecklistProgress.user_id == profile_user.id,
            ChecklistProgress.is_completed.is_(True),
        )
    )
    completed_checklist = int(checklist_result.scalar() or 0)

    # Get passed questions count (unique question_ids that have is_passed=True)
    questions_result = await db.execute(
        select(func.count(func.distinct(QuestionAttempt.question_id))).where(
            QuestionAttempt.user_id == profile_user.id,
            QuestionAttempt.is_passed.is_(True),
        )
    )
    passed_questions = int(questions_result.scalar() or 0)

    # Total completed = checklist + passed questions
    completed_topics = completed_checklist + passed_questions

    # Total items across all phases (checklist + questions = 247)
    total_topics = 247

    # Get streak info
    activity_result = await db.execute(
        select(UserActivity.activity_date)
        .where(UserActivity.user_id == profile_user.id)
        .order_by(UserActivity.activity_date.desc())
    )
    activity_dates = [row[0] for row in activity_result.all()]

    current_streak, longest_streak, streak_alive = calculate_streak_with_forgiveness(
        activity_dates, MAX_SKIP_DAYS
    )

    unique_dates = set(activity_dates)
    last_activity_date = activity_dates[0] if activity_dates else None

    streak = StreakResponse(
        current_streak=current_streak,
        longest_streak=longest_streak,
        total_activity_days=len(unique_dates),
        last_activity_date=last_activity_date,
        streak_alive=streak_alive,
    )

    # Get activity heatmap (last 270 days / ~9 months for cleaner display)
    from datetime import timedelta

    today = datetime.now(UTC).date()
    start_date = today - timedelta(days=270)

    heatmap_result = await db.execute(
        select(
            UserActivity.activity_date,
            UserActivity.activity_type,
            func.count(UserActivity.id).label("count"),
        )
        .where(
            UserActivity.user_id == profile_user.id,
            UserActivity.activity_date >= start_date,
        )
        .group_by(UserActivity.activity_date, UserActivity.activity_type)
        .order_by(UserActivity.activity_date)
    )
    rows = heatmap_result.all()

    date_activities: dict[str, dict] = {}
    total_activities = 0

    for row in rows:
        date_str = row.activity_date.isoformat()
        if date_str not in date_activities:
            date_activities[date_str] = {"count": 0, "types": set()}
        row_count: int = row[2]
        date_activities[date_str]["count"] += row_count
        date_activities[date_str]["types"].add(row.activity_type)
        total_activities += row_count

    heatmap_days = []
    for date_str, data in date_activities.items():
        heatmap_days.append(
            ActivityHeatmapDay(
                date=datetime.fromisoformat(date_str).date(),
                count=data["count"],
                activity_types=list(data["types"]),
            )
        )

    activity_heatmap = ActivityHeatmapResponse(
        days=heatmap_days,
        start_date=start_date,
        end_date=today,
        total_activities=total_activities,
    )

    # Calculate current phase from checklist progress
    # Get all completed checklist items for this user
    progress_result = await db.execute(
        select(ChecklistProgress.checklist_item_id).where(
            ChecklistProgress.user_id == profile_user.id,
            ChecklistProgress.is_completed.is_(True),
        )
    )
    completed_items = [row[0] for row in progress_result.all()]

    # Get passed questions grouped by phase (question_id format: phase{N}-topic{M}-q{X})
    passed_questions_result = await db.execute(
        select(func.distinct(QuestionAttempt.question_id)).where(
            QuestionAttempt.user_id == profile_user.id,
            QuestionAttempt.is_passed.is_(True),
        )
    )
    passed_question_ids = [row[0] for row in passed_questions_result.all()]

    # Count completed items per phase (item IDs follow pattern: phase{N}-topic{M}-check{X})
    # Known totals per phase (checklist + questions from content structure)
    # Total: 167 checklist + 80 questions = 247
    phase_totals = {0: 25, 1: 32, 2: 48, 3: 57, 4: 43, 5: 42}
    phase_completed: dict[int, int] = {}

    # Count checklist items per phase
    for item_id in completed_items:
        # Extract phase number from ID like "phase0-topic1-check1"
        if item_id.startswith("phase"):
            try:
                phase_num = int(item_id.split("-")[0].replace("phase", ""))
                phase_completed[phase_num] = phase_completed.get(phase_num, 0) + 1
            except (ValueError, IndexError):
                continue

    # Count passed questions per phase
    for question_id in passed_question_ids:
        # Extract phase number from ID like "phase0-topic1-q1"
        if question_id.startswith("phase"):
            try:
                phase_num = int(question_id.split("-")[0].replace("phase", ""))
                phase_completed[phase_num] = phase_completed.get(phase_num, 0) + 1
            except (ValueError, IndexError):
                continue

    # Determine current phase (first in-progress, or first not-started)
    current_phase = 0
    for phase_id in sorted(phase_totals.keys()):
        total = phase_totals[phase_id]
        completed = phase_completed.get(phase_id, 0)
        if completed == 0:
            # Not started - this is the current phase
            current_phase = phase_id
            break
        elif completed < total:
            # In progress - this is the current phase
            current_phase = phase_id
            break
        # else: completed == total, move to next phase
    else:
        # All phases completed, show last phase
        current_phase = max(phase_totals.keys())

    # Get validated GitHub submissions
    submissions_result = await db.execute(
        select(GitHubSubmission)
        .where(
            GitHubSubmission.user_id == profile_user.id,
            GitHubSubmission.is_validated.is_(True),
        )
        .order_by(GitHubSubmission.phase_id, GitHubSubmission.validated_at)
    )
    db_submissions = submissions_result.scalars().all()

    submissions = []
    for sub in db_submissions:
        requirement = get_requirement_by_id(sub.requirement_id)
        submissions.append(
            PublicSubmission(
                requirement_id=sub.requirement_id,
                submission_type=sub.submission_type,
                phase_id=sub.phase_id,
                submitted_url=sub.submitted_url,
                name=requirement.name if requirement else sub.requirement_id,
                validated_at=sub.validated_at,
            )
        )

    # Compute badges from progress and streak data
    earned_badges = compute_all_badges(
        phase_completed_counts=phase_completed,
        longest_streak=longest_streak,
    )
    badges = [
        BadgeResponse(
            id=badge.id,
            name=badge.name,
            description=badge.description,
            icon=badge.icon,
        )
        for badge in earned_badges
    ]

    return PublicProfileResponse(
        username=profile_user.github_username,
        first_name=profile_user.first_name,
        avatar_url=profile_user.avatar_url,
        current_phase=current_phase,
        completed_topics=completed_topics,
        total_topics=total_topics,
        streak=streak,
        activity_heatmap=activity_heatmap,
        member_since=profile_user.created_at,
        submissions=submissions,
        badges=badges,
    )
