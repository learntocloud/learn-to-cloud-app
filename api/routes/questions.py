"""Knowledge questions endpoints with LLM grading."""

import logging
from typing import Annotated

from fastapi import APIRouter, HTTPException, Path, Request
from slowapi import Limiter
from slowapi.util import get_remote_address

from core.auth import UserId
from core.database import DbSession
from schemas import (
    QuestionStatusResponse,
    QuestionSubmitRequest,
    QuestionSubmitResponse,
    TopicQuestionsStatusResponse,
)
from services.questions import (
    LLMGradingError,
    LLMServiceUnavailableError,
    get_all_questions_status,
    get_topic_questions_status,
    submit_question_answer,
)
from services.users import get_or_create_user

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/questions", tags=["questions"])

limiter = Limiter(key_func=get_remote_address)

ValidatedTopicId = Annotated[
    str,
    Path(max_length=100, pattern=r"^phase\d+-topic\d+$"),
]


@router.post("/submit", response_model=QuestionSubmitResponse)
@limiter.limit("10/minute")
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

    parts = submission.question_id.split("-")
    if len(parts) < 3:
        raise HTTPException(
            status_code=400,
            detail="Invalid question_id format. Expected: phase{N}-topic{M}-q{X}",
        )

    try:
        result = await submit_question_answer(
            db=db,
            user_id=user_id,
            topic_id=submission.topic_id,
            question_id=submission.question_id,
            user_answer=submission.user_answer,
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
    )


@router.post(
    "/submit-with-context",
    response_model=QuestionSubmitResponse,
)
@limiter.limit("10/minute")
async def submit_question_with_context_endpoint(
    request: Request,
    topic_id: str,
    question_id: str,
    question_prompt: str,
    expected_concepts: list[str],
    topic_name: str,
    user_answer: str,
    user_id: UserId,
    db: DbSession,
) -> QuestionSubmitResponse:
    """Submit an answer with full question context from frontend.

    This endpoint is used when the frontend passes the question details
    directly from the content JSON.
    """
    await get_or_create_user(db, user_id)

    try:
        result = await submit_question_answer(
            db=db,
            user_id=user_id,
            topic_id=topic_id,
            question_id=question_id,
            user_answer=user_answer,
            question_prompt=question_prompt,
            expected_concepts=expected_concepts,
            topic_name=topic_name,
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
    )


@router.get("/topic/{topic_id}/status", response_model=TopicQuestionsStatusResponse)
async def get_topic_questions_status_endpoint(
    topic_id: ValidatedTopicId,
    user_id: UserId,
    db: DbSession,
) -> TopicQuestionsStatusResponse:
    """Get the status of all questions in a topic for the current user.

    Returns which questions have been passed and attempt counts.
    """
    await get_or_create_user(db, user_id)

    status = await get_topic_questions_status(db, user_id, topic_id)

    return TopicQuestionsStatusResponse(
        topic_id=status.topic_id,
        questions=[
            QuestionStatusResponse(
                question_id=q.question_id,
                is_passed=q.is_passed,
                attempts_count=q.attempts_count,
                last_attempt_at=q.last_attempt_at,
            )
            for q in status.questions
        ],
        all_passed=status.all_passed,
        total_questions=status.total_questions,
        passed_questions=status.passed_questions,
    )


@router.get("/user/all-status")
async def get_all_questions_status_endpoint(
    user_id: UserId,
    db: DbSession,
) -> dict[str, TopicQuestionsStatusResponse]:
    """Get the status of all questions across all topics for the current user.

    Returns a dict mapping topic_id to question status.
    """
    await get_or_create_user(db, user_id)

    all_status = await get_all_questions_status(db, user_id)

    response = {}
    for topic_id, status in all_status.items():
        response[topic_id] = TopicQuestionsStatusResponse(
            topic_id=status.topic_id,
            questions=[
                QuestionStatusResponse(
                    question_id=q.question_id,
                    is_passed=q.is_passed,
                    attempts_count=q.attempts_count,
                    last_attempt_at=q.last_attempt_at,
                )
                for q in status.questions
            ],
            all_passed=status.all_passed,
            total_questions=status.total_questions,
            passed_questions=status.passed_questions,
        )

    return response
