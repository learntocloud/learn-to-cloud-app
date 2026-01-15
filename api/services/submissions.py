"""Submissions service for hands-on validation submissions.

This module handles:
- Submission creation/update with validation
- Retrieving submission status by user/phase
- Business logic for submission processing
- Data transformation for submissions

Routes should delegate submission business logic to this module.
"""

from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession

from models import Submission, SubmissionType
from repositories.submission import SubmissionRepository
from schemas import HandsOnRequirement
from services.github_hands_on_verification import parse_github_url
from services.hands_on_verification import (
    HANDS_ON_REQUIREMENTS,
    get_requirement_by_id,
    get_requirements_for_phase,
    validate_submission,
)


def group_submissions_by_phase(
    submissions: list[Submission],
) -> dict[int, list[Submission]]:
    """Group submissions by phase_id.

    This is business logic that transforms raw submission data
    into a structure useful for phase-based progress tracking.
    """
    by_phase: dict[int, list[Submission]] = {}
    for sub in submissions:
        if sub.phase_id not in by_phase:
            by_phase[sub.phase_id] = []
        by_phase[sub.phase_id].append(sub)
    return by_phase


def get_validated_requirement_ids(submissions: list[Submission]) -> set[str]:
    """Get set of requirement IDs that are validated.

    Used for checking which requirements a user has completed.
    """
    return {s.requirement_id for s in submissions if s.is_validated}


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


@dataclass
class PhaseSubmissionStatus:
    """Status of submissions for a phase."""

    phase_id: int
    submissions: list[Submission]
    requirements: list[HandsOnRequirement]
    has_requirements: bool
    all_validated: bool


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


async def get_all_submissions_by_user(
    db: AsyncSession,
    user_id: str,
) -> list[Submission]:
    """Get all submissions for a user.

    Args:
        db: Database session
        user_id: The user's ID

    Returns:
        List of all submissions
    """
    submission_repo = SubmissionRepository(db)
    return await submission_repo.get_all_by_user(user_id)


async def get_phase_submission_status(
    db: AsyncSession,
    user_id: str,
    phase_id: int,
) -> PhaseSubmissionStatus:
    """Get submission status for a specific phase.

    Args:
        db: Database session
        user_id: The user's ID
        phase_id: The phase ID

    Returns:
        PhaseSubmissionStatus with requirements and submissions
    """
    requirements = get_requirements_for_phase(phase_id)

    if not requirements:
        return PhaseSubmissionStatus(
            phase_id=phase_id,
            submissions=[],
            requirements=[],
            has_requirements=False,
            all_validated=True,
        )

    submission_repo = SubmissionRepository(db)
    submissions = await submission_repo.get_by_user_and_phase(user_id, phase_id)

    validated_requirement_ids = {
        s.requirement_id for s in submissions if s.is_validated
    }
    required_ids = {r.id for r in requirements}
    all_validated = required_ids.issubset(validated_requirement_ids)

    return PhaseSubmissionStatus(
        phase_id=phase_id,
        submissions=submissions,
        requirements=requirements,
        has_requirements=True,
        all_validated=all_validated,
    )


async def get_all_phases_submission_status(
    db: AsyncSession,
    user_id: str,
) -> list[PhaseSubmissionStatus]:
    """Get submission status for all phases in a single query.

    Args:
        db: Database session
        user_id: The user's ID

    Returns:
        List of PhaseSubmissionStatus for each phase with requirements
    """
    submission_repo = SubmissionRepository(db)

    all_submissions = await submission_repo.get_all_by_user(user_id)

    submissions_by_phase = group_submissions_by_phase(all_submissions)

    phases_status = []
    for phase_id, requirements in HANDS_ON_REQUIREMENTS.items():
        if not requirements:
            continue

        phase_submissions = submissions_by_phase.get(phase_id, [])

        validated_requirement_ids = {
            s.requirement_id for s in phase_submissions if s.is_validated
        }
        required_ids = {r.id for r in requirements}
        all_validated = required_ids.issubset(validated_requirement_ids)

        phases_status.append(
            PhaseSubmissionStatus(
                phase_id=phase_id,
                submissions=phase_submissions,
                requirements=requirements,
                has_requirements=True,
                all_validated=all_validated,
            )
        )

    return phases_status
