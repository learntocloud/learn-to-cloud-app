"""GitHub submission endpoints."""

from datetime import UTC, datetime

from fastapi import APIRouter, HTTPException, Request
from sqlalchemy import select

from shared.auth import UserId
from shared.database import DbSession, upsert_on_conflict
from shared.github import (
    GITHUB_REQUIREMENTS,
    get_requirement_by_id,
    get_requirements_for_phase,
    parse_github_url,
    validate_submission,
)
from shared.models import GitHubSubmission, SubmissionType
from shared.ratelimit import EXTERNAL_API_LIMIT, limiter
from shared.schemas import (
    AllPhasesGitHubRequirementsResponse,
    GitHubSubmissionRequest,
    GitHubSubmissionResponse,
    GitHubValidationResult,
    PhaseGitHubRequirementsResponse,
)

from .users import get_or_create_user

router = APIRouter(prefix="/api/github", tags=["github"])


@router.get("/requirements", response_model=AllPhasesGitHubRequirementsResponse)
async def get_all_github_requirements(
    user_id: UserId, db: DbSession
) -> AllPhasesGitHubRequirementsResponse:
    """Get GitHub requirements for ALL phases in a single query (bulk endpoint)."""
    # Get all user's submissions in ONE query
    result = await db.execute(
        select(GitHubSubmission).where(GitHubSubmission.user_id == user_id)
    )
    all_submissions = result.scalars().all()

    # Group submissions by phase_id
    submissions_by_phase: dict[int, list[GitHubSubmission]] = {}
    for sub in all_submissions:
        if sub.phase_id not in submissions_by_phase:
            submissions_by_phase[sub.phase_id] = []
        submissions_by_phase[sub.phase_id].append(sub)

    # Build response for each phase that has requirements
    phases_response = []
    for phase_id, requirements in GITHUB_REQUIREMENTS.items():
        if not requirements:
            continue

        phase_submissions = submissions_by_phase.get(phase_id, [])
        submission_responses = [
            GitHubSubmissionResponse.model_validate(s) for s in phase_submissions
        ]

        # Check if all requirements are validated
        validated_requirement_ids = {
            s.requirement_id for s in phase_submissions if s.is_validated
        }
        required_ids = {r.id for r in requirements}
        all_validated = required_ids.issubset(validated_requirement_ids)

        phases_response.append(
            PhaseGitHubRequirementsResponse(
                phase_id=phase_id,
                requirements=requirements,
                submissions=submission_responses,
                all_validated=all_validated,
            )
        )

    return AllPhasesGitHubRequirementsResponse(phases=phases_response)


@router.get("/requirements/{phase_id}", response_model=PhaseGitHubRequirementsResponse)
async def get_phase_github_requirements(
    phase_id: int, user_id: UserId, db: DbSession
) -> PhaseGitHubRequirementsResponse:
    """Get GitHub requirements and user's submissions for a phase."""
    requirements = get_requirements_for_phase(phase_id)

    if not requirements:
        return PhaseGitHubRequirementsResponse(
            phase_id=phase_id,
            requirements=[],
            submissions=[],
            all_validated=True,  # No requirements means nothing to validate
        )

    # Get user's existing submissions for this phase
    result = await db.execute(
        select(GitHubSubmission).where(
            GitHubSubmission.user_id == user_id,
            GitHubSubmission.phase_id == phase_id,
        )
    )
    submissions = result.scalars().all()

    submission_responses = [
        GitHubSubmissionResponse.model_validate(s) for s in submissions
    ]

    # Check if all requirements are validated
    validated_requirement_ids = {
        s.requirement_id for s in submissions if s.is_validated
    }
    required_ids = {r.id for r in requirements}
    all_validated = required_ids.issubset(validated_requirement_ids)

    return PhaseGitHubRequirementsResponse(
        phase_id=phase_id,
        requirements=requirements,
        submissions=submission_responses,
        all_validated=all_validated,
    )


@router.post("/submit", response_model=GitHubValidationResult)
@limiter.limit(EXTERNAL_API_LIMIT)
async def submit_github_validation(
    request: Request,
    submission: GitHubSubmissionRequest,
    user_id: UserId,
    db: DbSession,
) -> GitHubValidationResult:
    """Submit a GitHub URL for validation."""
    # Get the requirement
    requirement = get_requirement_by_id(submission.requirement_id)
    if not requirement:
        raise HTTPException(status_code=404, detail="Requirement not found")

    # Get user with github_username
    user = await get_or_create_user(db, user_id)

    # For GitHub-based submissions, require GitHub username
    if requirement.submission_type in (
        SubmissionType.PROFILE_README,
        SubmissionType.REPO_FORK,
    ):
        if not user.github_username:
            raise HTTPException(
                status_code=400,
                detail=(
                    "You need to link your GitHub account to submit. "
                    "Please sign out and sign in with GitHub."
                ),
            )

    # Validate the submission
    validation_result = await validate_submission(
        requirement=requirement,
        submitted_url=submission.submitted_url,
        expected_username=user.github_username,  # Can be None for deployed apps
    )

    now = datetime.now(UTC)

    # Extract username from URL for storage (only for GitHub URLs)
    parsed = parse_github_url(submission.submitted_url)
    github_username = parsed.username if parsed.is_valid else None

    # Concurrency-safe upsert for uq_user_requirement (user_id, requirement_id)
    values = {
        "user_id": user_id,
        "requirement_id": submission.requirement_id,
        "submission_type": requirement.submission_type,
        "phase_id": requirement.phase_id,
        "submitted_url": submission.submitted_url,
        "github_username": github_username,
        "is_validated": validation_result.is_valid,
        "validated_at": now if validation_result.is_valid else None,
        "updated_at": now,
    }

    await upsert_on_conflict(
        db=db,
        model=GitHubSubmission,
        values=values,
        index_elements=["user_id", "requirement_id"],
        update_fields=[
            "submission_type",
            "phase_id",
            "submitted_url",
            "github_username",
            "is_validated",
            "validated_at",
            "updated_at",
        ],
    )

    # Re-fetch for a consistent response (works for both insert and update)
    result = await db.execute(
        select(GitHubSubmission).where(
            GitHubSubmission.user_id == user_id,
            GitHubSubmission.requirement_id == submission.requirement_id,
        )
    )
    db_submission = result.scalar_one()

    return GitHubValidationResult(
        is_valid=validation_result.is_valid,
        message=validation_result.message,
        username_match=validation_result.username_match,
        repo_exists=validation_result.repo_exists,
        submission=GitHubSubmissionResponse.model_validate(db_submission),
    )


@router.get("/submissions", response_model=list[GitHubSubmissionResponse])
async def get_user_github_submissions(
    user_id: UserId, db: DbSession
) -> list[GitHubSubmissionResponse]:
    """Get all GitHub submissions for the current user."""
    result = await db.execute(
        select(GitHubSubmission).where(GitHubSubmission.user_id == user_id)
    )
    submissions = result.scalars().all()

    return [GitHubSubmissionResponse.model_validate(s) for s in submissions]
