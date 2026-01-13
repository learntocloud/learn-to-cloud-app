"""Knowledge questions endpoints with LLM grading."""

import logging
from typing import Annotated

from fastapi import APIRouter, HTTPException, Path, Request
from slowapi import Limiter
from slowapi.util import get_remote_address
from sqlalchemy import func, select

from shared.auth import UserId
from shared.database import DbSession
from shared.llm import grade_answer
from shared.models import ActivityType, QuestionAttempt, UserActivity
from shared.schemas import (
    QuestionStatusResponse,
    QuestionSubmitRequest,
    QuestionSubmitResponse,
    TopicQuestionsStatusResponse,
)

from .users import get_or_create_user

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/questions", tags=["questions"])

# Rate limiter for LLM calls (more restrictive than default)
limiter = Limiter(key_func=get_remote_address)


# Validated topic_id: e.g., "phase1-topic4"
ValidatedTopicId = Annotated[
    str,
    Path(max_length=100, pattern=r"^phase\d+-topic\d+$"),
]


@router.post("/submit", response_model=QuestionSubmitResponse)
@limiter.limit("10/minute")  # Stricter rate limit for LLM calls
async def submit_question_answer(
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

    # Extract topic and question info from IDs
    # question_id format: "phase1-topic4-q1"
    parts = submission.question_id.split("-")
    if len(parts) < 3:
        raise HTTPException(
            status_code=400,
            detail="Invalid question_id format. Expected: phase{N}-topic{M}-q{X}",
        )

    # For now, we'll use placeholder question data
    # In production, this would come from the frontend content or a questions API
    # The frontend will pass the question prompt and expected concepts
    # For MVP, we'll grade based on the answer alone with generic expectations

    # TODO: Fetch question details from content or add a questions endpoint
    # For now, use a generic grading approach
    question_prompt = "Explain the concept in your own words."
    expected_concepts = ["understanding", "explanation", "concept"]
    topic_name = submission.topic_id

    try:
        grade_result = await grade_answer(
            question_prompt=question_prompt,
            expected_concepts=expected_concepts,
            user_answer=submission.user_answer,
            topic_name=topic_name,
        )
    except ValueError as e:
        # API key not configured
        logger.error(f"LLM configuration error: {e}")
        raise HTTPException(
            status_code=503,
            detail="Question grading service is temporarily unavailable",
        )
    except Exception as e:
        logger.exception(f"LLM grading failed: {e}")
        raise HTTPException(
            status_code=500,
            detail="Failed to grade your answer. Please try again.",
        )

    # Save the attempt
    attempt = QuestionAttempt(
        user_id=user_id,
        topic_id=submission.topic_id,
        question_id=submission.question_id,
        user_answer=submission.user_answer,
        is_passed=grade_result.is_passed,
        llm_feedback=grade_result.feedback,
        confidence_score=grade_result.confidence_score,
    )
    db.add(attempt)

    # Log activity for streak tracking
    activity = UserActivity(
        user_id=user_id,
        activity_type=ActivityType.QUESTION_ATTEMPT,
        reference_id=submission.question_id,
    )
    db.add(activity)

    await db.commit()
    await db.refresh(attempt)

    return QuestionSubmitResponse(
        question_id=submission.question_id,
        is_passed=grade_result.is_passed,
        llm_feedback=grade_result.feedback,
        confidence_score=grade_result.confidence_score,
        attempt_id=attempt.id,
    )


@router.post(
    "/submit-with-context",
    response_model=QuestionSubmitResponse,
)
@limiter.limit("10/minute")
async def submit_question_with_context(
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
        grade_result = await grade_answer(
            question_prompt=question_prompt,
            expected_concepts=expected_concepts,
            user_answer=user_answer,
            topic_name=topic_name,
        )
    except ValueError as e:
        logger.error(f"LLM configuration error: {e}")
        raise HTTPException(
            status_code=503,
            detail="Question grading service is temporarily unavailable",
        )
    except Exception as e:
        logger.exception(f"LLM grading failed: {e}")
        raise HTTPException(
            status_code=500,
            detail="Failed to grade your answer. Please try again.",
        )

    # Save the attempt
    attempt = QuestionAttempt(
        user_id=user_id,
        topic_id=topic_id,
        question_id=question_id,
        user_answer=user_answer,
        is_passed=grade_result.is_passed,
        llm_feedback=grade_result.feedback,
        confidence_score=grade_result.confidence_score,
    )
    db.add(attempt)

    # Log activity
    activity = UserActivity(
        user_id=user_id,
        activity_type=ActivityType.QUESTION_ATTEMPT,
        reference_id=question_id,
    )
    db.add(activity)

    await db.commit()
    await db.refresh(attempt)

    return QuestionSubmitResponse(
        question_id=question_id,
        is_passed=grade_result.is_passed,
        llm_feedback=grade_result.feedback,
        confidence_score=grade_result.confidence_score,
        attempt_id=attempt.id,
    )


@router.get("/topic/{topic_id}/status", response_model=TopicQuestionsStatusResponse)
async def get_topic_questions_status(
    topic_id: ValidatedTopicId,
    user_id: UserId,
    db: DbSession,
) -> TopicQuestionsStatusResponse:
    """Get the status of all questions in a topic for the current user.

    Returns which questions have been passed and attempt counts.
    """
    await get_or_create_user(db, user_id)

    # Get all attempts for this topic, grouped by question_id
    result = await db.execute(
        select(
            QuestionAttempt.question_id,
            func.count(QuestionAttempt.id).label("attempts_count"),
            func.max(QuestionAttempt.created_at).label("last_attempt_at"),
        )
        .where(
            QuestionAttempt.user_id == user_id,
            QuestionAttempt.topic_id == topic_id,
        )
        .group_by(QuestionAttempt.question_id)
    )

    rows = result.all()

    # Also check if any attempt passed (simpler query)
    passed_result = await db.execute(
        select(QuestionAttempt.question_id)
        .where(
            QuestionAttempt.user_id == user_id,
            QuestionAttempt.topic_id == topic_id,
            QuestionAttempt.is_passed == True,  # noqa: E712
        )
        .distinct()
    )
    passed_questions = {row[0] for row in passed_result.all()}

    questions = []
    for row in rows:
        questions.append(
            QuestionStatusResponse(
                question_id=row.question_id,
                is_passed=row.question_id in passed_questions,
                attempts_count=int(row.attempts_count),
                last_attempt_at=row.last_attempt_at,
            )
        )

    # Note: total_questions should come from the content JSON
    # For now, we only know about questions that have been attempted
    passed_count = len(passed_questions)
    total = len(questions) if questions else 0

    return TopicQuestionsStatusResponse(
        topic_id=topic_id,
        questions=questions,
        all_passed=passed_count == total and total > 0,
        total_questions=total,
        passed_questions=passed_count,
    )


@router.get("/user/all-status")
async def get_all_questions_status(
    user_id: UserId,
    db: DbSession,
) -> dict[str, TopicQuestionsStatusResponse]:
    """Get the status of all questions across all topics for the current user.

    Returns a dict mapping topic_id to question status.
    """
    await get_or_create_user(db, user_id)

    # Get all passed questions grouped by topic
    result = await db.execute(
        select(
            QuestionAttempt.topic_id,
            QuestionAttempt.question_id,
        )
        .where(
            QuestionAttempt.user_id == user_id,
            QuestionAttempt.is_passed == True,  # noqa: E712
        )
        .distinct()
    )

    # Group by topic
    topic_passed: dict[str, set[str]] = {}
    for row in result.all():
        topic_id = row.topic_id
        if topic_id not in topic_passed:
            topic_passed[topic_id] = set()
        topic_passed[topic_id].add(row.question_id)

    # Build response
    response = {}
    for topic_id, passed_questions in topic_passed.items():
        passed_count = len(passed_questions)
        response[topic_id] = TopicQuestionsStatusResponse(
            topic_id=topic_id,
            questions=[
                QuestionStatusResponse(
                    question_id=q,
                    is_passed=True,
                    attempts_count=1,  # Simplified
                    last_attempt_at=None,
                )
                for q in passed_questions
            ],
            all_passed=True,  # Only returned if passed
            total_questions=passed_count,
            passed_questions=passed_count,
        )

    return response
