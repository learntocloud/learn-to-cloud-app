"""Knowledge questions endpoints with LLM grading."""

from datetime import UTC, datetime

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse

from core.auth import UserId
from core.database import DbSession
from core.ratelimit import EXTERNAL_API_LIMIT, limiter
from schemas import (
    QuestionSubmitRequest,
    QuestionSubmitResponse,
)
from services.questions_service import (
    GradingConceptsNotFoundError,
    LLMGradingError,
    LLMServiceUnavailableError,
    QuestionAttemptLimitExceeded,
    QuestionUnknownQuestionError,
    QuestionUnknownTopicError,
    QuestionValidationError,
    submit_question_answer,
)
from services.users_service import ensure_user_exists

router = APIRouter(prefix="/api/questions", tags=["questions"])


@router.post(
    "/submit",
    summary="Submit Question Answer",
    response_model=QuestionSubmitResponse,
    responses={
        404: {"description": "Topic or question not found"},
        400: {"description": "Missing grading configuration"},
        429: {
            "description": "Too many failed attempts - locked out temporarily",
            "content": {
                "application/json": {
                    "schema": {
                        "type": "object",
                        "properties": {
                            "detail": {"type": "string"},
                            "lockout_until": {
                                "type": "string",
                                "format": "date-time",
                            },
                            "attempts_used": {"type": "integer"},
                        },
                    }
                }
            },
        },
        503: {"description": "Question grading service temporarily unavailable"},
        500: {"description": "Internal grading error - retry suggested"},
    },
)
@limiter.limit(EXTERNAL_API_LIMIT)
async def submit_question_answer_endpoint(
    request: Request,
    submission: QuestionSubmitRequest,
    user_id: UserId,
    db: DbSession,
) -> QuestionSubmitResponse | JSONResponse:
    """Submit an answer to a knowledge question for LLM grading.

    The answer will be evaluated by Gemini and the user will receive
    immediate feedback on whether they passed.

    After 3 failed attempts on a question, the user is locked out for 1 hour.
    Questions already passed are exempt from attempt limiting.
    """
    await ensure_user_exists(db, user_id)

    try:
        result = await submit_question_answer(
            db=db,
            user_id=user_id,
            topic_id=submission.topic_id,
            question_id=submission.question_id,
            user_answer=submission.user_answer,
        )
    except (QuestionUnknownTopicError, QuestionUnknownQuestionError) as e:
        raise HTTPException(status_code=404, detail=str(e))
    except (QuestionValidationError, GradingConceptsNotFoundError) as e:
        raise HTTPException(status_code=400, detail=str(e))
    except QuestionAttemptLimitExceeded as e:
        # Calculate seconds until lockout expires for Retry-After header
        seconds_remaining = max(
            0, int((e.lockout_until - datetime.now(UTC)).total_seconds())
        )
        return JSONResponse(
            status_code=429,
            content={
                "detail": "Too many failed attempts. Please wait before trying again.",
                "lockout_until": e.lockout_until.isoformat(),
                "attempts_used": e.attempts_used,
            },
            headers={"Retry-After": str(seconds_remaining)},
        )
    except LLMServiceUnavailableError:
        raise HTTPException(
            status_code=503,
            detail="Question grading service is temporarily unavailable",
        )
    except LLMGradingError:
        raise HTTPException(
            status_code=500,
            detail="Failed to grade your answer. Please try again.",
        )

    return QuestionSubmitResponse(
        question_id=result.question_id,
        is_passed=result.is_passed,
        llm_feedback=result.feedback,
        confidence_score=result.confidence_score,
        attempt_id=result.attempt_id,
        attempts_used=result.attempts_used,
        lockout_until=result.lockout_until,
    )
