"""Submissions service for hands-on validation submissions.

This module handles:
- Submission creation/update with validation
- Data transformation helpers used by other services (e.g. progress/badges)
- Cooldown enforcement for rate-limited submission types (e.g., CODE_ANALYSIS)

Routes should delegate submission business logic to this module.
"""

from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession

from core import get_logger
from core.cache import invalidate_progress_cache
from core.config import get_settings
from core.telemetry import add_custom_attribute, log_metric, track_operation
from models import Submission, SubmissionType
from repositories.submission_repository import SubmissionRepository
from schemas import SubmissionData, SubmissionResult
from services.github_hands_on_verification_service import parse_github_url
from services.hands_on_verification_service import validate_submission
from services.phase_requirements_service import get_requirement_by_id

logger = get_logger(__name__)


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


@track_operation("hands_on_submission")
async def submit_validation(
    db: AsyncSession,
    user_id: str,
    requirement_id: str,
    submitted_value: str,
    github_username: str | None,
) -> SubmissionResult:
    """Submit a URL or token for hands-on validation.

    Raises:
        RequirementNotFoundError: If requirement doesn't exist.
        GitHubUsernameRequiredError: If GitHub username required but not provided.
        CooldownActiveError: If CODE_ANALYSIS submission is within cooldown period.
    """
    add_custom_attribute("submission.requirement_id", requirement_id)
    requirement = get_requirement_by_id(requirement_id)
    if not requirement:
        raise RequirementNotFoundError(f"Requirement not found: {requirement_id}")

    # Enforce cooldown for CODE_ANALYSIS submissions (1 hour by default)
    if requirement.submission_type == SubmissionType.CODE_ANALYSIS:
        submission_repo = SubmissionRepository(db)
        last_submission_time = await submission_repo.get_last_submission_time(
            user_id, requirement_id
        )

        if last_submission_time is not None:
            settings = get_settings()
            cooldown_seconds = settings.code_analysis_cooldown_seconds
            now = datetime.now(UTC)
            elapsed = (now - last_submission_time).total_seconds()
            remaining = int(cooldown_seconds - elapsed)

            if remaining > 0:
                logger.info(
                    "code_analysis.cooldown.active",
                    user_id=user_id,
                    requirement_id=requirement_id,
                    remaining_seconds=remaining,
                )
                raise CooldownActiveError(
                    f"Code analysis can only be submitted once per hour. "
                    f"Please try again in {remaining // 60} minutes.",
                    retry_after_seconds=remaining,
                )

    if requirement.submission_type in (
        SubmissionType.PROFILE_README,
        SubmissionType.REPO_FORK,
        SubmissionType.CTF_TOKEN,
        SubmissionType.CODE_ANALYSIS,
    ):
        if not github_username:
            raise GitHubUsernameRequiredError(
                "You need to link your GitHub account to submit. "
                "Please sign out and sign in with GitHub."
            )

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

    if validation_result.server_error:
        logger.info(
            "submission.server_error",
            user_id=user_id,
            requirement_id=requirement_id,
            message=validation_result.message,
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
    )

    phase = f"phase{requirement.phase_id}"
    if validation_result.is_valid:
        log_metric(
            "submissions.validated",
            1,
            {"phase": phase, "type": requirement.submission_type.value},
        )
        # Invalidate cache so dashboard/progress refreshes immediately
        invalidate_progress_cache(user_id)
    elif validation_result.server_error:
        log_metric(
            "submissions.server_error",
            1,
            {"phase": phase, "type": requirement.submission_type.value},
        )
    else:
        log_metric(
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
