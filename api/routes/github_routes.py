"""GitHub submission endpoints."""

from fastapi import APIRouter, HTTPException, Request

from core.auth import UserId
from core.database import DbSession
from core.ratelimit import EXTERNAL_API_LIMIT, limiter
from schemas import (
    HandsOnSubmissionRequest,
    HandsOnSubmissionResponse,
    HandsOnValidationResult,
)
from services.submissions_service import (
    GitHubUsernameRequiredError,
    RequirementNotFoundError,
    submit_validation,
)
from services.users_service import get_or_create_user

router = APIRouter(prefix="/api/github", tags=["github"])


@router.post(
    "/submit",
    response_model=HandsOnValidationResult,
    status_code=201,
    responses={
        400: {"description": "GitHub username required to submit"},
        401: {"description": "Not authenticated"},
        404: {"description": "Requirement not found"},
    },
)
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
        username_match=result.username_match or False,
        repo_exists=result.repo_exists or False,
        submission=HandsOnSubmissionResponse.model_validate(result.submission),
    )
