"""GitHub submission endpoints."""

from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException
from sqlalchemy import select

from shared import (
    DbSession,
    UserId,
    GitHubSubmission,
    GitHubSubmissionRequest,
    GitHubSubmissionResponse,
    GitHubValidationResult,
    PhaseGitHubRequirementsResponse,
    AllPhasesGitHubRequirementsResponse,
    get_requirements_for_phase,
    get_requirement_by_id,
    validate_submission,
    parse_github_url,
    GITHUB_REQUIREMENTS,
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
    validated_requirement_ids = {s.requirement_id for s in submissions if s.is_validated}
    required_ids = {r.id for r in requirements}
    all_validated = required_ids.issubset(validated_requirement_ids)

    return PhaseGitHubRequirementsResponse(
        phase_id=phase_id,
        requirements=requirements,
        submissions=submission_responses,
        all_validated=all_validated,
    )


@router.post("/submit", response_model=GitHubValidationResult)
async def submit_github_validation(
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
    if requirement.submission_type.value in ("profile_readme", "repo_fork"):
        if not user.github_username:
            raise HTTPException(
                status_code=400,
                detail="You need to link your GitHub account to submit. Please sign out and sign in with GitHub.",
            )

    # Validate the submission
    validation_result = await validate_submission(
        requirement=requirement,
        submitted_url=submission.submitted_url,
        expected_username=user.github_username,  # Can be None for deployed apps
    )

    now = datetime.now(timezone.utc)

    # Check for existing submission
    result = await db.execute(
        select(GitHubSubmission).where(
            GitHubSubmission.user_id == user_id,
            GitHubSubmission.requirement_id == submission.requirement_id,
        )
    )
    existing = result.scalar_one_or_none()

    # Extract username from URL for storage (only for GitHub URLs)
    parsed = parse_github_url(submission.submitted_url)
    github_username = parsed.username if parsed.is_valid else None

    if existing:
        # Update existing submission
        existing.submitted_url = submission.submitted_url
        existing.github_username = github_username
        existing.is_validated = validation_result.is_valid
        existing.validated_at = now if validation_result.is_valid else None
        existing.updated_at = now
        db_submission = existing
    else:
        # Create new submission
        db_submission = GitHubSubmission(
            user_id=user_id,
            requirement_id=submission.requirement_id,
            submission_type=requirement.submission_type.value,
            phase_id=requirement.phase_id,
            submitted_url=submission.submitted_url,
            github_username=github_username,
            is_validated=validation_result.is_valid,
            validated_at=now if validation_result.is_valid else None,
        )
        db.add(db_submission)

    await db.flush()
    await db.refresh(db_submission)

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
