"""GitHub submission endpoints."""

from dataclasses import asdict

from fastapi import APIRouter, HTTPException, Request

from core.auth import UserId
from core.database import DbSession
from core.ratelimit import EXTERNAL_API_LIMIT, limiter
from schemas import (
    HandsOnSubmissionRequest,
    HandsOnSubmissionResponse,
    HandsOnValidationResult,
)
from services.submissions import (
    GitHubUsernameRequiredError,
    RequirementNotFoundError,
    submit_validation,
)
from services.users import get_or_create_user

router = APIRouter(prefix="/api/github", tags=["github"])


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
        username_match=result.username_match
        if result.username_match is not None
        else False,
        repo_exists=result.repo_exists if result.repo_exists is not None else False,
        submission=HandsOnSubmissionResponse.model_validate(asdict(result.submission)),
    )
