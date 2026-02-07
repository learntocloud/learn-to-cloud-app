"""Submissions service for hands-on validation submissions.

This module handles:
- Submission creation/update with validation
- Data transformation helpers used by other services (e.g. progress/badges)
- Cooldown enforcement for rate-limited submission types (e.g., CODE_ANALYSIS)
- Escalating cooldowns on consecutive failures (doubles per failure, capped at 4h)
- Daily submission cap across all requirements (default 20/day)
- Already-validated short-circuit (skip re-verification for passed requirements)
- Concurrent request protection via per-user+requirement locks

Routes should delegate submission business logic to this module.
"""

import asyncio
import json
from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession

from core.cache import invalidate_progress_cache
from core.config import get_settings
from core.telemetry import add_custom_attribute, log_business_event, track_operation
from core.wide_event import set_wide_event_fields
from models import Submission, SubmissionType
from repositories.submission_repository import SubmissionRepository
from schemas import SubmissionData, SubmissionResult
from services.github_hands_on_verification_service import parse_github_url
from services.hands_on_verification_service import validate_submission
from services.phase_requirements_service import get_requirement_by_id

# =============================================================================
# Concurrent Request Protection
# =============================================================================
# In-memory locks to prevent concurrent AI calls for the same user+requirement.
# This prevents wasting quota on race conditions (e.g., user opens multiple tabs).

_submission_locks: dict[tuple[int, str], asyncio.Lock] = {}
_locks_lock = asyncio.Lock()  # Protects _submission_locks dict itself


async def _get_submission_lock(user_id: int, requirement_id: str) -> asyncio.Lock:
    """Get or create a lock for a specific user+requirement combination.

    This ensures only one validation can run at a time for each user+requirement,
    preventing race conditions that waste AI quota.
    """
    key = (user_id, requirement_id)
    async with _locks_lock:
        if key not in _submission_locks:
            _submission_locks[key] = asyncio.Lock()
        return _submission_locks[key]


class ConcurrentSubmissionError(Exception):
    """Raised when a submission is already in progress for this user+requirement."""

    pass


def _to_submission_data(submission: Submission) -> SubmissionData:
    return SubmissionData(
        id=submission.id,
        requirement_id=submission.requirement_id,
        submission_type=submission.submission_type,
        phase_id=submission.phase_id,
        submitted_value=submission.submitted_value,
        extracted_username=submission.extracted_username,
        is_validated=submission.is_validated,
        validated_at=submission.validated_at,
        verification_completed=submission.verification_completed,
        created_at=submission.created_at,
    )


def get_validated_ids_by_phase(
    submissions: list[Submission],
) -> dict[int, set[str]]:
    """Get validated requirement IDs grouped by phase.

    Used for determining phase completion status for badges and progress.
    """
    by_phase: dict[int, set[str]] = {}
    for sub in submissions:
        if sub.is_validated:
            if sub.phase_id not in by_phase:
                by_phase[sub.phase_id] = set()
            by_phase[sub.phase_id].add(sub.requirement_id)
    return by_phase


class RequirementNotFoundError(Exception):
    pass


class GitHubUsernameRequiredError(Exception):
    pass


class CooldownActiveError(Exception):
    """Raised when a submission is attempted during cooldown period."""

    def __init__(self, message: str, retry_after_seconds: int):
        super().__init__(message)
        self.retry_after_seconds = retry_after_seconds


class DailyLimitExceededError(Exception):
    """Raised when a user exceeds the daily submission cap."""

    def __init__(self, message: str, limit: int):
        super().__init__(message)
        self.limit = limit


class AlreadyValidatedError(Exception):
    """Raised when re-submitting a requirement that is already validated."""

    pass


# =============================================================================
# Escalating Cooldown Tracking
# =============================================================================
# In-memory counter for consecutive failures per user+requirement.
# Resets on successful validation or server restart.
# This is per-worker, which is acceptable — it's defense-in-depth on top
# of the DB-based cooldown.

_failure_counts: dict[tuple[int, str], int] = {}

_MAX_COOLDOWN_SECONDS = 14400  # 4 hours — cap for escalating cooldowns


@track_operation("hands_on_submission")
async def submit_validation(
    db: AsyncSession,
    user_id: int,
    requirement_id: str,
    submitted_value: str,
    github_username: str | None,
) -> SubmissionResult:
    """Submit a URL or token for hands-on validation.

    Raises:
        RequirementNotFoundError: If requirement doesn't exist.
        AlreadyValidatedError: If requirement is already validated.
        DailyLimitExceededError: If user exceeded daily submission cap.
        GitHubUsernameRequiredError: If GitHub username required but not provided.
        CooldownActiveError: If submission is within cooldown period.
        ConcurrentSubmissionError: If validation is already in progress for this
            user+requirement (prevents race conditions).
    """
    add_custom_attribute("submission.requirement_id", requirement_id)
    requirement = get_requirement_by_id(requirement_id)
    if not requirement:
        raise RequirementNotFoundError(f"Requirement not found: {requirement_id}")

    submission_repo = SubmissionRepository(db)

    # --- Already-validated short-circuit ---
    # If the user already passed this requirement, skip re-verification.
    # This saves AI quota and prevents unnecessary reprocessing.
    existing = await submission_repo.get_by_user_and_requirement(
        user_id, requirement_id
    )
    if existing is not None and existing.is_validated:
        set_wide_event_fields(
            submission_already_validated=True,
            submission_type=requirement.submission_type.value,
        )
        raise AlreadyValidatedError("You have already completed this requirement.")

    # --- Global daily submission cap ---
    settings = get_settings()
    today_count = await submission_repo.count_submissions_today(user_id)
    if today_count >= settings.daily_submission_limit:
        set_wide_event_fields(
            submission_daily_limit_exceeded=True,
            submission_daily_count=today_count,
        )
        raise DailyLimitExceededError(
            f"You have reached the daily limit of {settings.daily_submission_limit} "
            f"submissions. Please try again tomorrow.",
            limit=settings.daily_submission_limit,
        )

    # --- Escalating cooldown enforcement ---
    # Base cooldown is 1 hour. Each consecutive failure doubles it, capped at 4h.
    last_submission_time = await submission_repo.get_last_submission_time(
        user_id, requirement_id
    )

    if last_submission_time is not None:
        base_cooldown = (
            settings.code_analysis_cooldown_seconds
            if requirement.submission_type
            in (SubmissionType.CODE_ANALYSIS, SubmissionType.DEVOPS_ANALYSIS)
            else settings.submission_cooldown_seconds
        )

        # Escalate cooldown based on consecutive failures
        failure_key = (user_id, requirement_id)
        failure_count = _failure_counts.get(failure_key, 0)
        cooldown_seconds = min(
            base_cooldown * (2**failure_count),
            _MAX_COOLDOWN_SECONDS,
        )

        now = datetime.now(UTC)
        elapsed = (now - last_submission_time).total_seconds()
        remaining = int(cooldown_seconds - elapsed)

        if remaining > 0:
            set_wide_event_fields(
                submission_cooldown_active=True,
                submission_cooldown_remaining_seconds=remaining,
                submission_cooldown_multiplier=2**failure_count,
                submission_type=requirement.submission_type.value,
            )
            raise CooldownActiveError(
                f"Verification can only be submitted once per "
                f"{cooldown_seconds // 3600}h {(cooldown_seconds % 3600) // 60}m. "
                f"Please try again in {remaining // 60} minutes.",
                retry_after_seconds=remaining,
            )

    if requirement.submission_type in (
        SubmissionType.PROFILE_README,
        SubmissionType.REPO_FORK,
        SubmissionType.CTF_TOKEN,
        SubmissionType.NETWORKING_TOKEN,
        SubmissionType.CODE_ANALYSIS,
        SubmissionType.DEVOPS_ANALYSIS,
    ):
        if not github_username:
            raise GitHubUsernameRequiredError(
                "You need to link your GitHub account to submit. "
                "Please sign out and sign in with GitHub."
            )

    # Prevent concurrent submissions for the same user+requirement.
    # This avoids wasting AI quota if user has multiple tabs open.
    submission_lock = await _get_submission_lock(user_id, requirement_id)
    if submission_lock.locked():
        set_wide_event_fields(
            submission_concurrent_blocked=True,
            submission_type=requirement.submission_type.value,
        )
        raise ConcurrentSubmissionError(
            "A verification is already in progress. Please wait for it to complete."
        )

    async with submission_lock:
        validation_result = await validate_submission(
            requirement=requirement,
            submitted_value=submitted_value,
            expected_username=github_username,
        )

        # Extract username from submission for audit/display purposes.
        # For GitHub URLs: parse the username from the URL itself.
        # For CTF tokens: the token embeds the expected username, so we store
        # the authenticated user's GitHub username (tokens are user-specific).
        extracted_username = None
        if requirement.submission_type != SubmissionType.CTF_TOKEN:
            parsed = parse_github_url(submitted_value)
            extracted_username = parsed.username if parsed.is_valid else None
        else:
            extracted_username = github_username

        # Track whether verification actually completed (not blocked by server error).
        # Only completed verifications count toward cooldowns.
        verification_completed = not validation_result.server_error

        # Serialize task results for persistence (CODE_ANALYSIS submissions)
        feedback_json = None
        if validation_result.task_results:
            feedback_json = json.dumps(
                [t.model_dump() for t in validation_result.task_results]
            )

        if validation_result.server_error:
            set_wide_event_fields(
                submission_server_error=True,
                submission_server_error_message=validation_result.message,
            )

        submission_repo = SubmissionRepository(db)

        # Repository handles upsert atomically (PostgreSQL ON CONFLICT)
        db_submission = await submission_repo.upsert(
            user_id=user_id,
            requirement_id=requirement_id,
            submission_type=requirement.submission_type,
            phase_id=requirement.phase_id,
            submitted_value=submitted_value,
            extracted_username=extracted_username,
            is_validated=validation_result.is_valid,
            verification_completed=verification_completed,
            feedback_json=feedback_json,
        )

        # --- Update escalating cooldown tracker ---
        failure_key = (user_id, requirement_id)
        phase = f"phase{requirement.phase_id}"
        if validation_result.is_valid:
            # Reset failure counter on success
            _failure_counts.pop(failure_key, None)
            log_business_event(
                "submissions.validated",
                1,
                {"phase": phase, "type": requirement.submission_type.value},
            )
            # Invalidate cache so dashboard/progress refreshes immediately
            invalidate_progress_cache(user_id)
        elif validation_result.server_error:
            # Don't escalate on server errors — not the user's fault
            log_business_event(
                "submissions.server_error",
                1,
                {"phase": phase, "type": requirement.submission_type.value},
            )
        else:
            # Increment failure counter for escalating cooldowns
            _failure_counts[failure_key] = _failure_counts.get(failure_key, 0) + 1
            log_business_event(
                "submissions.failed",
                1,
                {"phase": phase, "type": requirement.submission_type.value},
            )

        return SubmissionResult(
            submission=_to_submission_data(db_submission),
            is_valid=validation_result.is_valid,
            message=validation_result.message,
            username_match=validation_result.username_match,
            repo_exists=validation_result.repo_exists,
            task_results=validation_result.task_results,
        )
