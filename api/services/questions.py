"""Questions service for knowledge check grading and progress tracking.

This module handles:
- Question submission and grading via LLM
- Recording question attempts with activity logging

Routes should delegate question business logic to this module.
"""

import logging
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession

from models import ActivityType
from repositories.activity import ActivityRepository
from repositories.progress import QuestionAttemptRepository
from services.content import get_topic_by_id
from services.llm import grade_answer

logger = logging.getLogger(__name__)


@dataclass
class QuestionGradeResult:
    """Result of grading a question answer."""

    question_id: str
    is_passed: bool
    feedback: str
    confidence_score: float
    attempt_id: int


class LLMServiceUnavailableError(Exception):
    """Raised when LLM service is not configured or unavailable."""

    pass


class LLMGradingError(Exception):
    """Raised when LLM grading fails."""

    pass


class QuestionValidationError(Exception):
    """Raised when question submission validation fails."""


class QuestionUnknownTopicError(QuestionValidationError):
    """Raised when a topic_id doesn't exist in content."""


class QuestionUnknownQuestionError(QuestionValidationError):
    """Raised when a question_id doesn't exist in the given topic."""


async def submit_question_answer(
    db: AsyncSession,
    user_id: str,
    topic_id: str,
    question_id: str,
    user_answer: str,
) -> QuestionGradeResult:
    """Submit an answer for LLM grading and record the attempt.

    Args:
        db: Database session
        user_id: The user's ID
        topic_id: The topic ID (e.g., "phase1-topic4")
        question_id: The question ID (e.g., "phase1-topic4-q1")
        user_answer: The user's answer text
    Returns:
        QuestionGradeResult with grading details

    Raises:
        LLMServiceUnavailableError: If LLM service not configured
        LLMGradingError: If grading fails
    """
    question_repo = QuestionAttemptRepository(db)
    activity_repo = ActivityRepository(db)

    topic = get_topic_by_id(topic_id)
    if topic is None:
        raise QuestionUnknownTopicError(f"Unknown topic_id: {topic_id}")

    question = next((q for q in topic.questions if q.id == question_id), None)
    if question is None:
        raise QuestionUnknownQuestionError(
            f"Unknown question_id: {question_id} for topic_id: {topic_id}"
        )

    prompt = question.prompt
    concepts = list(question.expected_concepts)
    name = topic.name

    try:
        grade_result = await grade_answer(
            question_prompt=prompt,
            expected_concepts=concepts,
            user_answer=user_answer,
            topic_name=name,
        )
    except ValueError as e:
        logger.error(f"LLM configuration error: {e}")
        raise LLMServiceUnavailableError(
            "Question grading service is temporarily unavailable"
        )
    except Exception as e:
        logger.exception(f"LLM grading failed: {e}")
        raise LLMGradingError("Failed to grade your answer. Please try again.")

    attempt = await question_repo.create(
        user_id=user_id,
        topic_id=topic_id,
        question_id=question_id,
        is_passed=grade_result.is_passed,
        user_answer=user_answer,
        llm_feedback=grade_result.feedback,
        confidence_score=grade_result.confidence_score,
    )

    today = datetime.now(UTC).date()
    await activity_repo.log_activity(
        user_id=user_id,
        activity_type=ActivityType.QUESTION_ATTEMPT,
        activity_date=today,
        reference_id=question_id,
    )

    return QuestionGradeResult(
        question_id=question_id,
        is_passed=grade_result.is_passed,
        feedback=grade_result.feedback,
        confidence_score=grade_result.confidence_score,
        attempt_id=attempt.id,
    )
