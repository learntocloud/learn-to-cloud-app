"""Knowledge questions endpoints with LLM grading."""

from fastapi import APIRouter, HTTPException, Request

from core.auth import UserId
from core.database import DbSession
from core.ratelimit import EXTERNAL_API_LIMIT, limiter
from schemas import (
    QuestionSubmitRequest,
    QuestionSubmitResponse,
)
from services.questions_service import (
    LLMGradingError,
    LLMServiceUnavailableError,
    QuestionValidationError,
    submit_question_answer,
)
from services.users_service import get_or_create_user

router = APIRouter(prefix="/api/questions", tags=["questions"])


@router.post("/submit", response_model=QuestionSubmitResponse)
@limiter.limit(EXTERNAL_API_LIMIT)
async def submit_question_answer_endpoint(
    request: Request,
    submission: QuestionSubmitRequest,
    user_id: UserId,
    db: DbSession,
) -> QuestionSubmitResponse:
    """Submit an answer to a knowledge question for LLM grading.

    The answer will be evaluated by Gemini and the user will receive
    immediate feedback on whether they passed.
    """
    await get_or_create_user(db, user_id)

    try:
        result = await submit_question_answer(
            db=db,
            user_id=user_id,
            topic_id=submission.topic_id,
            question_id=submission.question_id,
            user_answer=submission.user_answer,
        )
    except QuestionValidationError as e:
        raise HTTPException(status_code=400, detail=str(e))
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
    )
