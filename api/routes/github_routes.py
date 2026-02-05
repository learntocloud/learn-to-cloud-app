"""GitHub submission endpoints."""

from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse

from core.auth import UserId
from core.config import get_settings
from core.database import DbSession
from core.ratelimit import EXTERNAL_API_LIMIT, limiter
from schemas import (
    HandsOnSubmissionRequest,
    HandsOnSubmissionResponse,
    HandsOnValidationResult,
    SubmissionType,
)
from services.submissions_service import (
    CooldownActiveError,
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
        429: {"description": "Rate limited or cooldown active"},
    },
)
@limiter.limit(EXTERNAL_API_LIMIT)
async def submit_github_validation(
    request: Request,
    submission: HandsOnSubmissionRequest,
    user_id: UserId,
    db: DbSession,
) -> HandsOnValidationResult | JSONResponse:
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
    except CooldownActiveError as e:
        return JSONResponse(
            status_code=429,
            content={"detail": str(e)},
            headers={"Retry-After": str(e.retry_after_seconds)},
        )

    # Calculate next retry time for cooldown display
    next_retry = _get_next_retry_at(result.submission)

    return HandsOnValidationResult(
        is_valid=result.is_valid,
        message=result.message,
        username_match=result.username_match or False,
        repo_exists=result.repo_exists or False,
        submission=HandsOnSubmissionResponse.model_validate(result.submission),
        task_results=result.task_results,
        next_retry_at=next_retry,
    )


def _get_next_retry_at(submission: HandsOnSubmissionResponse | None) -> str | None:
    """Calculate when next retry is allowed after a submission."""
    if not submission:
        return None

    settings = get_settings()
    cooldown_seconds = (
        settings.code_analysis_cooldown_seconds
        if submission.submission_type == SubmissionType.CODE_ANALYSIS
        else settings.submission_cooldown_seconds
    )
    retry_at = datetime.now(UTC) + timedelta(seconds=cooldown_seconds)
    return retry_at.isoformat()
