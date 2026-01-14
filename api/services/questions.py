"""Questions service for knowledge check grading and progress tracking.

This module handles:
- Question submission and grading via LLM
- Recording question attempts with activity logging
- Retrieving question status and statistics

Routes should delegate question business logic to this module.
"""

import logging
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession

from models import ActivityType
from repositories.activity import ActivityRepository
from repositories.progress import QuestionAttemptRepository
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

@dataclass
class QuestionStatus:
    """Status of a single question."""

    question_id: str
    is_passed: bool
    attempts_count: int
    last_attempt_at: datetime | None

@dataclass
class TopicQuestionsStatus:
    """Status of all questions in a topic."""

    topic_id: str
    questions: list[QuestionStatus]
    all_passed: bool
    total_questions: int
    passed_questions: int

class LLMServiceUnavailableError(Exception):
    """Raised when LLM service is not configured or unavailable."""

    pass

class LLMGradingError(Exception):
    """Raised when LLM grading fails."""

    pass

async def submit_question_answer(
    db: AsyncSession,
    user_id: str,
    topic_id: str,
    question_id: str,
    user_answer: str,
    question_prompt: str | None = None,
    expected_concepts: list[str] | None = None,
    topic_name: str | None = None,
) -> QuestionGradeResult:
    """Submit an answer for LLM grading and record the attempt.

    Args:
        db: Database session
        user_id: The user's ID
        topic_id: The topic ID (e.g., "phase1-topic4")
        question_id: The question ID (e.g., "phase1-topic4-q1")
        user_answer: The user's answer text
        question_prompt: Optional question prompt (defaults to generic)
        expected_concepts: Optional list of expected concepts
        topic_name: Optional topic name for context

    Returns:
        QuestionGradeResult with grading details

    Raises:
        LLMServiceUnavailableError: If LLM service not configured
        LLMGradingError: If grading fails
    """
    question_repo = QuestionAttemptRepository(db)
    activity_repo = ActivityRepository(db)

    prompt = question_prompt or "Explain the concept in your own words."
    concepts = expected_concepts or ["understanding", "explanation", "concept"]
    name = topic_name or topic_id

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
    )
    attempt.llm_feedback = grade_result.feedback
    attempt.confidence_score = grade_result.confidence_score

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

async def get_topic_questions_status(
    db: AsyncSession,
    user_id: str,
    topic_id: str,
) -> TopicQuestionsStatus:
    """Get the status of all questions in a topic for a user.

    Args:
        db: Database session
        user_id: The user's ID
        topic_id: The topic ID

    Returns:
        TopicQuestionsStatus with question statuses
    """
    question_repo = QuestionAttemptRepository(db)

    stats = await question_repo.get_topic_stats(user_id, topic_id)
    passed_questions = await question_repo.get_passed_question_ids(user_id, topic_id)

    questions = []
    for stat in stats:
        questions.append(
            QuestionStatus(
                question_id=stat["question_id"],
                is_passed=stat["question_id"] in passed_questions,
                attempts_count=stat["attempts_count"],
                last_attempt_at=stat["last_attempt_at"],
            )
        )

    passed_count = len(passed_questions)
    total = len(questions) if questions else 0

    return TopicQuestionsStatus(
        topic_id=topic_id,
        questions=questions,
        all_passed=passed_count == total and total > 0,
        total_questions=total,
        passed_questions=passed_count,
    )

async def get_all_questions_status(
    db: AsyncSession,
    user_id: str,
) -> dict[str, TopicQuestionsStatus]:
    """Get the status of all questions across all topics for a user.

    Args:
        db: Database session
        user_id: The user's ID

    Returns:
        Dict mapping topic_id to TopicQuestionsStatus
    """
    question_repo = QuestionAttemptRepository(db)
    topic_passed = await question_repo.get_all_passed_by_user(user_id)

    response = {}
    for topic_id, passed_questions in topic_passed.items():
        passed_count = len(passed_questions)
        response[topic_id] = TopicQuestionsStatus(
            topic_id=topic_id,
            questions=[
                QuestionStatus(
                    question_id=q,
                    is_passed=True,
                    attempts_count=1,
                    last_attempt_at=None,
                )
                for q in passed_questions
            ],
            all_passed=True,
            total_questions=passed_count,
            passed_questions=passed_count,
        )

    return response
