"""Submissions service for hands-on validation submissions.

This module handles:
- Submission creation/update with validation
- Data transformation helpers used by other services (e.g. progress)
- Daily submission cap across all requirements (default 20/day)
- Already-validated short-circuit (skip re-verification for passed requirements)
- Concurrent request protection via per-user+requirement locks
- DB connection release during long-running LLM calls

Routes should delegate submission business logic to this module.
"""

from __future__ import annotations

import asyncio
import json
import logging
from dataclasses import dataclass

from cachetools import TTLCache
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from core.cache import invalidate_progress_cache
from core.config import get_settings
from core.metrics import SUBMISSION_DAILY_LIMIT_COUNTER
from models import Submission, SubmissionType
from repositories.progress_denormalized_repository import UserPhaseProgressRepository
from repositories.submission_repository import SubmissionRepository
from schemas import (
    HandsOnRequirement,
    PhaseSubmissionContext,
    SubmissionData,
    SubmissionResult,
)
from services.verification.dispatcher import validate_submission
from services.verification.github_profile import parse_github_url
from services.verification.requirements import (
    get_phase_id_for_requirement,
    get_prerequisite_phase,
    get_requirement_by_id,
    get_requirement_ids_for_phase,
)

logger = logging.getLogger(__name__)

_LOCK_TTL = 7200  # 2 hours
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
        validation_message=submission.validation_message,
        cloud_provider=submission.cloud_provider,
        created_at=submission.created_at,
        updated_at=submission.updated_at,
    )


async def get_phase_submission_context(
    db: AsyncSession,
    user_id: int,
    phase_id: int,
) -> PhaseSubmissionContext:
    """Build submission context for rendering a phase page.

    Fetches all submissions for the user in a phase, converts them to
    DTOs, and parses stored feedback JSON into template-ready summaries.
    Calculates remaining time for LLM-based submission types.

    Returns:
        PhaseSubmissionContext with submissions and feedback keyed by
        requirement ID.
    """
    repo = SubmissionRepository(db)
    raw_submissions = await repo.get_by_user_and_phase(user_id, phase_id)

    submissions_by_req: dict[str, SubmissionData] = {}
    feedback_by_req: dict[str, dict[str, object]] = {}

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

                feedback_by_req[sub.requirement_id] = {
                    "tasks": tasks,
                    "passed": passed,
                }
            except (json.JSONDecodeError, TypeError):
                logger.debug(
                    "submission.feedback_parse_failed",
                    extra={"requirement_id": sub.requirement_id},
                )

    return PhaseSubmissionContext(
        submissions_by_req=submissions_by_req,
        feedback_by_req=feedback_by_req,
    )


class RequirementNotFoundError(Exception):
    pass


class GitHubUsernameRequiredError(Exception):
    pass


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


class DuplicatePrError(Exception):
    """Raised when the same PR URL is used for a different requirement."""

    def __init__(self, message: str, conflicting_requirement_id: str):
        super().__init__(message)
        self.conflicting_requirement_id = conflicting_requirement_id


class PriorPhaseNotCompleteError(Exception):
    """Raised when submitting for a phase whose prerequisite isn't fully verified."""

    def __init__(self, message: str, prerequisite_phase: int):
        super().__init__(message)
        self.prerequisite_phase = prerequisite_phase


# Caps the number of concurrent LLM verification calls across all users.
# Prevents connection pool exhaustion: without this, N simultaneous users could
# each hold a DB connection for 30-120s waiting on the LLM, starving all other
# routes.  The semaphore is checked *before* acquiring the DB write session.
_LLM_MAX_CONCURRENT = 3
_llm_semaphore = asyncio.Semaphore(_LLM_MAX_CONCURRENT)


@dataclass(frozen=True, slots=True)
class _PreValidationContext:
    """Data collected during pre-validation checks.

    Returned by ``_check_submission_preconditions`` so callers don't
    repeat the same DB queries.
    """

    requirement: HandsOnRequirement
    phase_id: int
    existing_data: SubmissionData | None


async def _check_submission_preconditions(
    session_maker: async_sessionmaker[AsyncSession],
    user_id: int,
    requirement_id: str,
    github_username: str | None,
    submitted_value: str | None = None,
) -> _PreValidationContext:
    """Shared pre-validation checks for submission paths.

    Validates requirement existence, already-validated status, phase gating,
    daily cap, PR uniqueness, and GitHub username requirement.

    Opens a short-lived DB session for reads, then releases it before
    returning.  Raises the same exceptions as ``submit_validation``.
    """
    requirement = get_requirement_by_id(requirement_id)
    if not requirement:
        raise RequirementNotFoundError(f"Requirement not found: {requirement_id}")

    phase_id = get_phase_id_for_requirement(requirement_id)
    if phase_id is None:
        raise RequirementNotFoundError(
            f"Requirement not mapped to a phase: {requirement_id}"
        )

    async with session_maker() as read_session:
        submission_repo = SubmissionRepository(read_session)

        existing = await submission_repo.get_by_user_and_requirement(
            user_id, requirement_id
        )
        if existing is not None and existing.is_validated:
            raise AlreadyValidatedError("You have already completed this requirement.")

        # Sequential phase gating
        prereq_phase = get_prerequisite_phase(phase_id)
        if prereq_phase is not None:
            prereq_req_ids = get_requirement_ids_for_phase(prereq_phase)
            if prereq_req_ids:
                all_done = await submission_repo.are_all_requirements_validated(
                    user_id, prereq_req_ids
                )
                if not all_done:
                    raise PriorPhaseNotCompleteError(
                        f"You must complete all Phase {prereq_phase} "
                        f"verifications before submitting for Phase {phase_id}.",
                        prerequisite_phase=prereq_phase,
                    )

        # Global daily submission cap
        settings = get_settings()
        today_count = await submission_repo.count_submissions_today(user_id)
        if today_count >= settings.daily_submission_limit:
            SUBMISSION_DAILY_LIMIT_COUNTER.add(
                1,
                {"user_id": str(user_id)},
            )
            raise DailyLimitExceededError(
                f"You have reached the daily limit of "
                f"{settings.daily_submission_limit} "
                f"submissions. Please try again tomorrow.",
                limit=settings.daily_submission_limit,
                existing_submission=_to_submission_data(existing) if existing else None,
            )

        # PR uniqueness: same PR URL cannot be reused for a different
        # requirement within the same phase.
        if submitted_value and requirement.submission_type == SubmissionType.PR_REVIEW:
            conflicting = await submission_repo.find_validated_by_value_in_phase(
                user_id, phase_id, submitted_value, requirement_id
            )
            if conflicting:
                raise DuplicatePrError(
                    "This PR was already used for a different requirement. "
                    "Each task must have its own PR — follow the branching "
                    "workflow in the journal-starter README.",
                    conflicting_requirement_id=conflicting,
                )

        existing_data = _to_submission_data(existing) if existing else None
    # read_session is now closed — connection returned to pool

    if (
        requirement.submission_type
        in (
            SubmissionType.GITHUB_PROFILE,
            SubmissionType.PROFILE_README,
            SubmissionType.REPO_FORK,
            SubmissionType.CTF_TOKEN,
            SubmissionType.NETWORKING_TOKEN,
            SubmissionType.CI_STATUS,
            SubmissionType.DEVOPS_ANALYSIS,
            SubmissionType.SECURITY_SCANNING,
            SubmissionType.PR_REVIEW,
        )
        and not github_username
    ):
        raise GitHubUsernameRequiredError(
            "You need to link your GitHub account to submit. "
            "Please sign out and sign in with GitHub."
        )

    return _PreValidationContext(
        requirement=requirement,
        phase_id=phase_id,
        existing_data=existing_data,
    )


async def pre_validate_submission(
    session_maker: async_sessionmaker[AsyncSession],
    user_id: int,
    requirement_id: str,
    submitted_value: str,
    github_username: str | None,
) -> None:
    """Run pre-validation checks without starting the actual verification.

    This is the fast path (<100ms) that checks:
    - Requirement exists
    - Not already validated
    - Phase gating
    - Daily submission cap
    - PR uniqueness
    - GitHub username required

    Used by the async LLM submission path to validate before kicking off
    a background task.  Raises the same exceptions as submit_validation.
    """
    await _check_submission_preconditions(
        session_maker, user_id, requirement_id, github_username, submitted_value
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
        ConcurrentSubmissionError: If validation is already in progress for this
            user+requirement (prevents race conditions).
    """
    ctx = await _check_submission_preconditions(
        session_maker, user_id, requirement_id, github_username, submitted_value
    )
    requirement = ctx.requirement
    phase_id = ctx.phase_id
    existing_data = ctx.existing_data

    # Prevent concurrent submissions for the same user+requirement.
    submission_lock = await _get_submission_lock(user_id, requirement_id)
    if submission_lock.locked():
        raise ConcurrentSubmissionError(
            "A verification is already in progress. Please wait for it to complete."
        )

    async with submission_lock:
        # ── Run validation (NO DB session held) ─────────────────────────
        # Verification can take 10-120s for LLM-backed types.  We run it
        # outside any DB session so it doesn't pin a connection pool slot.
        # A global semaphore caps LLM concurrency to prevent overwhelming
        # the endpoint.
        logger.info(
            "llm.semaphore.acquiring",
            extra={
                "user_id": user_id,
                "requirement_id": requirement_id,
                "waiting": max(
                    0,
                    _LLM_MAX_CONCURRENT - _llm_semaphore._value,
                ),
            },
        )

        async with _llm_semaphore:
            validation_result = await validate_submission(
                requirement=requirement,
                submitted_value=submitted_value,
                expected_username=github_username,
            )

        extracted_username = None
        if requirement.submission_type in (
            SubmissionType.CTF_TOKEN,
            SubmissionType.NETWORKING_TOKEN,
        ):
            extracted_username = github_username
        else:
            parsed = parse_github_url(submitted_value)
            extracted_username = parsed.username if parsed.is_valid else None

        verification_completed = not validation_result.server_error

        feedback_json = None
        if validation_result.task_results:
            feedback_json = json.dumps(
                [t.model_dump() for t in validation_result.task_results]
            )

        # Persist the user-facing message so it survives page reloads.
        validation_message = (
            validation_result.message if not validation_result.is_valid else None
        )

        # Cloud provider (populated for multi-cloud labs like networking).
        cloud_provider = validation_result.cloud_provider

        # ── Phase 3: Persist result (short-lived session) ───────────────
        # A fresh session is opened just for the upsert, keeping connection
        # hold time to ~50ms.
        async with session_maker() as write_session:
            write_repo = SubmissionRepository(write_session)

            db_submission = await write_repo.create(
                user_id=user_id,
                requirement_id=requirement_id,
                submission_type=requirement.submission_type,
                phase_id=phase_id,
                submitted_value=submitted_value,
                extracted_username=extracted_username,
                is_validated=validation_result.is_valid,
                verification_completed=verification_completed,
                feedback_json=feedback_json,
                validation_message=validation_message,
                cloud_provider=cloud_provider,
            )

            # Update denormalized counts for newly validated submissions
            if validation_result.is_valid and not (
                existing_data and existing_data.is_validated
            ):
                denorm_repo = UserPhaseProgressRepository(write_session)
                await denorm_repo.increment_submissions(user_id, phase_id, delta=1)

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
