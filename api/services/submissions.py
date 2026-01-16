"""Submissions service for hands-on validation submissions.

This module handles:
- Submission creation/update with validation
- Data transformation helpers used by other services (e.g. progress/badges)

Routes should delegate submission business logic to this module.
"""

from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession

from models import Submission, SubmissionType
from repositories.submission import SubmissionRepository
from services.github_hands_on_verification import parse_github_url
from services.hands_on_verification import get_requirement_by_id, validate_submission


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
    """Result of a hands-on submission."""

    submission: Submission
    is_valid: bool
    message: str
    username_match: bool | None
    repo_exists: bool | None


class RequirementNotFoundError(Exception):
    """Raised when a requirement ID doesn't exist."""

    pass


class GitHubUsernameRequiredError(Exception):
    """Raised when GitHub username is required but not provided."""

    pass


async def submit_validation(
    db: AsyncSession,
    user_id: str,
    requirement_id: str,
    submitted_value: str,
    github_username: str | None,
) -> SubmissionResult:
    """Submit a URL or token for hands-on validation.

    Args:
        db: Database session
        user_id: The user's ID
        requirement_id: The requirement being submitted for
        submitted_value: The URL or token submitted
        github_username: The user's GitHub username (if linked)

    Returns:
        SubmissionResult with validation outcome and saved submission

    Raises:
        RequirementNotFoundError: If requirement doesn't exist
        GitHubUsernameRequiredError: If GitHub username required but not provided
    """
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

    return SubmissionResult(
        submission=db_submission,
        is_valid=validation_result.is_valid,
        message=validation_result.message,
        username_match=validation_result.username_match,
        repo_exists=validation_result.repo_exists,
    )
