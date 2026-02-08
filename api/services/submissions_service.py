"""Submissions service for hands-on validation submissions.

This module handles:
- Submission creation/update with validation
- Data transformation helpers used by other services (e.g. progress/badges)
- Cooldown enforcement for rate-limited submission types (e.g., CODE_ANALYSIS)
- Daily submission cap across all requirements (default 20/day)
- Already-validated short-circuit (skip re-verification for passed requirements)
- Concurrent request protection via per-user+requirement locks
- DB connection release during long-running LLM calls

Routes should delegate submission business logic to this module.
"""

import asyncio
import json
import logging
from datetime import UTC, datetime

from cachetools import TTLCache
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from core.cache import invalidate_progress_cache
from core.config import get_settings
from models import Submission, SubmissionType
from repositories.submission_repository import SubmissionRepository
from schemas import PhaseSubmissionContext, SubmissionData, SubmissionResult
from services.github_hands_on_verification_service import parse_github_url
from services.hands_on_verification_service import validate_submission
from services.phase_requirements_service import get_requirement_by_id

logger = logging.getLogger(__name__)

# =============================================================================
# Concurrent Request Protection
# =============================================================================
# In-memory locks to prevent concurrent AI calls for the same user+requirement.
# This prevents wasting quota on race conditions (e.g., user opens multiple tabs).
# TTLCache auto-evicts entries after 2 hours to prevent unbounded memory growth.

_LOCK_TTL = 7200  # 2 hours — comfortably above the max cooldown (1 hour)
_submission_locks: TTLCache[tuple[int, str], asyncio.Lock] = TTLCache(
    maxsize=2000, ttl=_LOCK_TTL
)
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
        feedback_json=submission.feedback_json,
        created_at=submission.created_at,
        updated_at=submission.updated_at,
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


async def get_phase_submission_context(
    db: AsyncSession,
    user_id: int,
    phase_id: int,
) -> PhaseSubmissionContext:
    """Build submission context for rendering a phase page.

    Fetches all submissions for the user in a phase, converts them to
    DTOs, and parses stored feedback JSON into template-ready summaries.
    Calculates remaining cooldown for LLM-based submission types.

    Returns:
        PhaseSubmissionContext with submissions and feedback keyed by
        requirement ID.
    """
    repo = SubmissionRepository(db)
    raw_submissions = await repo.get_by_user_and_phase(user_id, phase_id)

    submissions_by_req: dict[str, SubmissionData] = {}
    feedback_by_req: dict[str, dict[str, object]] = {}

    settings = get_settings()
    now = datetime.now(UTC)

    for sub in raw_submissions:
        sub_data = _to_submission_data(sub)
        submissions_by_req[sub.requirement_id] = sub_data

        if sub.feedback_json and not sub.is_validated:
            try:
                raw_tasks = json.loads(sub.feedback_json)
                tasks = [
                    {
                        "name": t.get("task_name", ""),
                        "passed": t.get("passed", False),
                        "message": t.get("feedback", ""),
                    }
                    for t in raw_tasks
                ]
                passed = sum(1 for t in tasks if t["passed"])

                cooldown_remaining = None
                if sub.updated_at and sub.verification_completed:
                    if sub.submission_type in (
                        SubmissionType.CODE_ANALYSIS,
                        SubmissionType.DEVOPS_ANALYSIS,
                    ):
                        elapsed = (now - sub.updated_at).total_seconds()
                        remaining = int(
                            settings.code_analysis_cooldown_seconds - elapsed
                        )
                        if remaining > 0:
                            cooldown_remaining = remaining

                feedback_by_req[sub.requirement_id] = {
                    "tasks": tasks,
                    "passed": passed,
                    "cooldown_seconds": cooldown_remaining,
                }
            except (json.JSONDecodeError, TypeError):
                pass

    return PhaseSubmissionContext(
        submissions_by_req=submissions_by_req,
        feedback_by_req=feedback_by_req,
    )


class RequirementNotFoundError(Exception):
    pass


class GitHubUsernameRequiredError(Exception):
    pass


class CooldownActiveError(Exception):
    """Raised when a submission is attempted during cooldown period."""

    def __init__(
        self,
        message: str,
        retry_after_seconds: int,
        existing_submission: SubmissionData | None = None,
    ):
        super().__init__(message)
        self.retry_after_seconds = retry_after_seconds
        self.existing_submission = existing_submission


class DailyLimitExceededError(Exception):
    """Raised when a user exceeds the daily submission cap."""

    def __init__(
        self,
        message: str,
        limit: int,
        existing_submission: SubmissionData | None = None,
    ):
        super().__init__(message)
        self.limit = limit
        self.existing_submission = existing_submission


class AlreadyValidatedError(Exception):
    """Raised when re-submitting a requirement that is already validated."""

    pass


# =============================================================================
# Global LLM Concurrency Limit
# =============================================================================
# Caps the number of concurrent LLM verification calls across all users.
# Prevents connection pool exhaustion: without this, N simultaneous users could
# each hold a DB connection for 30-120s waiting on the LLM, starving all other
# routes.  The semaphore is checked *before* acquiring the DB write session.
_LLM_MAX_CONCURRENT = 3
_llm_semaphore = asyncio.Semaphore(_LLM_MAX_CONCURRENT)


def _is_llm_submission(submission_type: SubmissionType) -> bool:
    """Return True for submission types that involve long-running LLM calls."""
    return submission_type in (
        SubmissionType.CODE_ANALYSIS,
        SubmissionType.DEVOPS_ANALYSIS,
    )


async def submit_validation(
    session_maker: async_sessionmaker[AsyncSession],
    user_id: int,
    requirement_id: str,
    submitted_value: str,
    github_username: str | None,
) -> SubmissionResult:
    """Submit a URL or token for hands-on validation.

    DB connection lifecycle:
        This function uses short-lived sessions instead of holding a single
        session for the entire request.  The pre-validation checks use one
        session (released in ~50ms), then the LLM call runs with NO session
        held (30-120s), and finally a fresh session is opened for the upsert
        (~50ms).  This prevents long-running LLM calls from pinning a
        connection pool slot.

    Args:
        session_maker: Factory for creating short-lived DB sessions.
        user_id: Authenticated user ID.
        requirement_id: The hands-on requirement being submitted.
        submitted_value: URL, token, or other submission payload.
        github_username: GitHub username from OAuth (required for most types).

    Raises:
        RequirementNotFoundError: If requirement doesn't exist.
        AlreadyValidatedError: If requirement is already validated.
        DailyLimitExceededError: If user exceeded daily submission cap.
        GitHubUsernameRequiredError: If GitHub username required but not provided.
        CooldownActiveError: If submission is within cooldown period.
        ConcurrentSubmissionError: If validation is already in progress for this
            user+requirement (prevents race conditions).
    """
    requirement = get_requirement_by_id(requirement_id)
    if not requirement:
        raise RequirementNotFoundError(f"Requirement not found: {requirement_id}")

    # ── Phase 1: Pre-validation DB reads (short-lived session) ──────────
    # Connection is held for only a few quick queries, then released before
    # the potentially long-running LLM call.
    async with session_maker() as read_session:
        submission_repo = SubmissionRepository(read_session)

        # --- Already-validated short-circuit ---
        existing = await submission_repo.get_by_user_and_requirement(
            user_id, requirement_id
        )
        if existing is not None and existing.is_validated:
            raise AlreadyValidatedError("You have already completed this requirement.")

        # --- Global daily submission cap ---
        settings = get_settings()
        today_count = await submission_repo.count_submissions_today(user_id)
        if today_count >= settings.daily_submission_limit:
            raise DailyLimitExceededError(
                f"You have reached the daily limit of "
                f"{settings.daily_submission_limit} "
                f"submissions. Please try again tomorrow.",
                limit=settings.daily_submission_limit,
                existing_submission=_to_submission_data(existing) if existing else None,
            )

        # --- Cooldown enforcement (LLM submissions only) ---
        # Lightweight verifications (CTF, profile, fork, etc.) are instant
        # and free — the daily cap is sufficient protection.  LLM-based
        # verifications cost money and hold a semaphore slot, so they get
        # an additional per-requirement cooldown.
        if requirement.submission_type in (
            SubmissionType.CODE_ANALYSIS,
            SubmissionType.DEVOPS_ANALYSIS,
        ):
            last_submission_time = await submission_repo.get_last_submission_time(
                user_id, requirement_id
            )
        else:
            last_submission_time = None

        # Convert to DTO while session is still open so it's safe to use
        # after the session closes (detached from SQLAlchemy).
        existing_data = _to_submission_data(existing) if existing else None
    # read_session is now closed — connection returned to pool

    if last_submission_time is not None:
        cooldown_seconds = settings.code_analysis_cooldown_seconds

        now = datetime.now(UTC)
        elapsed = (now - last_submission_time).total_seconds()
        remaining = int(cooldown_seconds - elapsed)

        if remaining > 0:
            minutes = remaining // 60
            seconds = remaining % 60
            wait_str = f"{minutes}m {seconds}s" if minutes else f"{seconds}s"
            raise CooldownActiveError(
                f"Please wait {wait_str} before resubmitting.",
                retry_after_seconds=remaining,
                existing_submission=existing_data,
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
    submission_lock = await _get_submission_lock(user_id, requirement_id)
    if submission_lock.locked():
        raise ConcurrentSubmissionError(
            "A verification is already in progress. Please wait for it to complete."
        )

    async with submission_lock:
        # ── Phase 2: Run validation (NO DB session held) ────────────────
        # LLM-based validations (CODE_ANALYSIS, DEVOPS_ANALYSIS) can take
        # 30-120s.  We run them outside any DB session so they don't pin a
        # connection pool slot.  A global semaphore caps concurrency to
        # prevent overwhelming the LLM endpoint.
        use_semaphore = _is_llm_submission(requirement.submission_type)

        if use_semaphore:
            logger.info(
                "llm.semaphore.acquiring",
                extra={
                    "user_id": user_id,
                    "requirement_id": requirement_id,
                    "waiting": _LLM_MAX_CONCURRENT - _llm_semaphore._value,
                },
            )

        async with _llm_semaphore if use_semaphore else _noop_context():
            validation_result = await validate_submission(
                requirement=requirement,
                submitted_value=submitted_value,
                expected_username=github_username,
            )

        # Extract username from submission for audit/display purposes.
        extracted_username = None
        if requirement.submission_type != SubmissionType.CTF_TOKEN:
            parsed = parse_github_url(submitted_value)
            extracted_username = parsed.username if parsed.is_valid else None
        else:
            extracted_username = github_username

        verification_completed = not validation_result.server_error

        feedback_json = None
        if validation_result.task_results:
            feedback_json = json.dumps(
                [t.model_dump() for t in validation_result.task_results]
            )

        # ── Phase 3: Persist result (short-lived session) ───────────────
        # A fresh session is opened just for the upsert, keeping connection
        # hold time to ~50ms.
        async with session_maker() as write_session:
            write_repo = SubmissionRepository(write_session)

            db_submission = await write_repo.upsert(
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
            await write_session.commit()

        if validation_result.is_valid:
            invalidate_progress_cache(user_id)

        logger.info(
            "submission.validated",
            extra={
                "user_id": user_id,
                "requirement_id": requirement_id,
                "is_valid": validation_result.is_valid,
                "verification_completed": verification_completed,
            },
        )

        return SubmissionResult(
            submission=_to_submission_data(db_submission),
            is_valid=validation_result.is_valid,
            message=validation_result.message,
            username_match=validation_result.username_match,
            repo_exists=validation_result.repo_exists,
            task_results=validation_result.task_results,
        )


class _noop_context:
    """Async context manager that does nothing — used to skip the semaphore."""

    async def __aenter__(self) -> None:
        pass

    async def __aexit__(self, *args: object) -> None:
        pass
