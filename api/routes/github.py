"""GitHub submission endpoints."""

from fastapi import APIRouter, HTTPException, Request

from core.auth import UserId
from core.database import DbSession
from core.ratelimit import EXTERNAL_API_LIMIT, limiter
from schemas import (
    AllPhasesHandsOnRequirementsResponse,
    HandsOnSubmissionRequest,
    HandsOnSubmissionResponse,
    HandsOnValidationResult,
    PhaseHandsOnRequirementsResponse,
)
from services.submissions import (
    GitHubUsernameRequiredError,
    RequirementNotFoundError,
    get_all_phases_submission_status,
    get_all_submissions_by_user,
    get_phase_submission_status,
    submit_validation,
)
from services.users import get_or_create_user

router = APIRouter(prefix="/api/github", tags=["github"])

@router.get("/requirements", response_model=AllPhasesHandsOnRequirementsResponse)
async def get_all_github_requirements(
    user_id: UserId, db: DbSession
) -> AllPhasesHandsOnRequirementsResponse:
    """Get hands-on requirements for ALL phases in a single query (bulk endpoint)."""
    phases_status = await get_all_phases_submission_status(db, user_id)

    phases_response = [
        PhaseHandsOnRequirementsResponse(
            phase_id=status.phase_id,
            requirements=status.requirements,
            submissions=[
                HandsOnSubmissionResponse.model_validate(s) for s in status.submissions
            ],
            has_requirements=status.has_requirements,
            all_validated=status.all_validated,
        )
        for status in phases_status
    ]

    return AllPhasesHandsOnRequirementsResponse(phases=phases_response)

@router.get("/requirements/{phase_id}", response_model=PhaseHandsOnRequirementsResponse)
async def get_phase_github_requirements(
    phase_id: int, user_id: UserId, db: DbSession
) -> PhaseHandsOnRequirementsResponse:
    """Get hands-on requirements and user's submissions for a phase."""
    status = await get_phase_submission_status(db, user_id, phase_id)

    return PhaseHandsOnRequirementsResponse(
        phase_id=status.phase_id,
        requirements=status.requirements,
        submissions=[
            HandsOnSubmissionResponse.model_validate(s) for s in status.submissions
        ],
        has_requirements=status.has_requirements,
        all_validated=status.all_validated,
    )

@router.post("/submit", response_model=HandsOnValidationResult)
@limiter.limit(EXTERNAL_API_LIMIT)
async def submit_github_validation(
    request: Request,
    submission: HandsOnSubmissionRequest,
    user_id: UserId,
    db: DbSession,
) -> HandsOnValidationResult:
    """Submit a URL or token for hands-on validation."""
    user = await get_or_create_user(db, user_id)

    try:
        result = await submit_validation(
            db=db,
            user_id=user_id,
            requirement_id=submission.requirement_id,
            submitted_value=submission.submitted_value,
            github_username=user.github_username,
        )
    except RequirementNotFoundError:
        raise HTTPException(status_code=404, detail="Requirement not found")
    except GitHubUsernameRequiredError as e:
        raise HTTPException(status_code=400, detail=str(e))

    return HandsOnValidationResult(
        is_valid=result.is_valid,
        message=result.message,
        username_match=result.username_match,
        repo_exists=result.repo_exists,
        submission=HandsOnSubmissionResponse.model_validate(result.submission),
    )

@router.get("/submissions", response_model=list[HandsOnSubmissionResponse])
async def get_user_submissions(
    user_id: UserId, db: DbSession
) -> list[HandsOnSubmissionResponse]:
    """Get all hands-on submissions for the current user."""
    submissions = await get_all_submissions_by_user(db, user_id)

    return [HandsOnSubmissionResponse.model_validate(s) for s in submissions]
