"""Submissions service for hands-on validation submissions.

This module handles:
- Submission creation/update with validation
- Data transformation helpers used by other services (e.g. progress/badges)

Routes should delegate submission business logic to this module.
"""

from dataclasses import dataclass
from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncSession

from core.cache import invalidate_progress_cache
from core.telemetry import add_custom_attribute, log_metric, track_operation
from models import Submission, SubmissionType
from repositories.submission_repository import SubmissionRepository
from services.github_hands_on_verification_service import parse_github_url
from services.hands_on_verification_service import validate_submission
from services.phase_requirements_service import get_requirement_by_id


@dataclass(frozen=True)
class SubmissionData:
    """DTO for a hands-on submission (service-layer return type)."""

    id: int
    requirement_id: str
    submission_type: SubmissionType
    phase_id: int
    submitted_value: str
    extracted_username: str | None
    is_validated: bool
    validated_at: datetime | None
    created_at: datetime


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


@dataclass
class SubmissionResult:
    submission: SubmissionData
    is_valid: bool
    message: str
    username_match: bool | None
    repo_exists: bool | None


class RequirementNotFoundError(Exception):
    pass


class GitHubUsernameRequiredError(Exception):
    pass


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
    """
    add_custom_attribute("submission.requirement_id", requirement_id)
    requirement = get_requirement_by_id(requirement_id)
    if not requirement:
        raise RequirementNotFoundError(f"Requirement not found: {requirement_id}")

    if requirement.submission_type in (
        SubmissionType.PROFILE_README,
        SubmissionType.REPO_FORK,
        SubmissionType.CTF_TOKEN,
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

    extracted_username = None
    if requirement.submission_type != SubmissionType.CTF_TOKEN:
        parsed = parse_github_url(submitted_value)
        extracted_username = parsed.username if parsed.is_valid else None
    else:
        extracted_username = github_username

    submission_repo = SubmissionRepository(db)
    db_submission = await submission_repo.upsert(
        user_id=user_id,
        requirement_id=requirement_id,
        submission_type=requirement.submission_type,
        phase_id=requirement.phase_id,
        submitted_value=submitted_value,
        extracted_username=extracted_username,
        is_validated=validation_result.is_valid,
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
    )
