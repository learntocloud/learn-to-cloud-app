"""Questions service for knowledge check grading and progress tracking.

This module handles:
- Question submission and grading via LLM
- Recording question attempts with activity logging
- Attempt limiting with lockout periods

Routes should delegate question business logic to this module.

Grading concepts (expected_concepts) are embedded in the content JSON files
alongside question prompts. This simplifies the architecture by keeping all
content in one place (frontend/public/content/).
"""

from datetime import UTC, datetime, timedelta

from sqlalchemy.ext.asyncio import AsyncSession

from core import get_logger
from core.cache import invalidate_progress_cache
from core.config import get_settings
from core.telemetry import add_custom_attribute, log_metric, track_operation
from models import ActivityType
from repositories.progress_repository import QuestionAttemptRepository
from schemas import QuestionGradeResult
from services.activity_service import log_activity
from services.content_service import get_topic_by_id
from services.llm_service import GeminiServiceUnavailable, grade_answer

logger = get_logger(__name__)


class LLMServiceUnavailableError(Exception):
    """Raised when LLM service is not configured or unavailable."""


class LLMGradingError(Exception):
    """Raised when LLM grading fails."""


class QuestionValidationError(Exception):
    """Raised when question submission validation fails."""


class QuestionUnknownTopicError(QuestionValidationError):
    """Raised when a topic_id doesn't exist in content."""


class QuestionUnknownQuestionError(QuestionValidationError):
    """Raised when a question_id doesn't exist in the given topic."""


class GradingConceptsNotFoundError(QuestionValidationError):
    """Raised when grading concepts are not found for a question."""


class QuestionAttemptLimitExceeded(Exception):
    """Raised when user exceeds max attempts and is locked out.

    Attributes:
        lockout_until: When the lockout expires (UTC)
        attempts_used: Number of failed attempts in current window
    """

    def __init__(self, lockout_until: datetime, attempts_used: int) -> None:
        self.lockout_until = lockout_until
        self.attempts_used = attempts_used
        super().__init__(
            f"Too many failed attempts. Try again after {lockout_until.isoformat()}"
        )


@track_operation("question_submission")
async def submit_question_answer(
    db: AsyncSession,
    user_id: str,
    topic_id: str,
    question_id: str,
    user_answer: str,
) -> QuestionGradeResult:
    """Submit an answer for LLM grading and record the attempt.

    Args:
        topic_id: Topic ID (e.g., "phase1-topic4")
        question_id: Question ID (e.g., "phase1-topic4-q1")
        user_answer: The user's answer text

    Raises:
        QuestionUnknownTopicError: If topic_id doesn't exist in content
        QuestionUnknownQuestionError: If question_id doesn't exist in topic
        GradingConceptsNotFoundError: If expected_concepts not configured
        QuestionAttemptLimitExceeded: If user exceeded max attempts (locked out)
        LLMServiceUnavailableError: If LLM service not configured
        LLMGradingError: If grading fails
    """
    settings = get_settings()
    add_custom_attribute("question.topic_id", topic_id)
    add_custom_attribute("question.id", question_id)
    question_repo = QuestionAttemptRepository(db)

    topic = get_topic_by_id(topic_id)
    if topic is None:
        raise QuestionUnknownTopicError(f"Unknown topic_id: {topic_id}")

    question = next((q for q in topic.questions if q.id == question_id), None)
    if question is None:
        raise QuestionUnknownQuestionError(
            f"Unknown question_id: {question_id} for topic_id: {topic_id}"
        )

    if not question.expected_concepts:
        logger.error(f"Grading concepts not found for question: {question_id}")
        raise GradingConceptsNotFoundError(
            f"Grading data not configured for question: {question_id}"
        )

    # Skip attempt limiting if user already passed this question (re-practice allowed)
    already_passed = await question_repo.has_passed_question(user_id, question_id)
    failed_attempts_before = 0
    if not already_passed:
        # Check attempt limit - count failures in the lockout window
        lockout_window_start = datetime.now(UTC) - timedelta(
            minutes=settings.quiz_lockout_minutes
        )
        failed_attempts_before = await question_repo.count_recent_failed_attempts(
            user_id=user_id,
            question_id=question_id,
            since=lockout_window_start,
        )
        if failed_attempts_before >= settings.quiz_max_attempts:
            # Get oldest failure to calculate when lockout expires
            oldest_failure = await question_repo.get_oldest_recent_failure(
                user_id=user_id,
                question_id=question_id,
                since=lockout_window_start,
            )
            # Lockout expires when oldest failure "ages out" of the rolling window
            lockout_until = (oldest_failure or datetime.now(UTC)) + timedelta(
                minutes=settings.quiz_lockout_minutes
            )
            log_metric(
                "questions.lockout",
                1,
                {"question_id": question_id, "attempts": str(failed_attempts_before)},
            )
            raise QuestionAttemptLimitExceeded(
                lockout_until=lockout_until,
                attempts_used=failed_attempts_before,
            )

    try:
        grade_result = await grade_answer(
            question_prompt=question.prompt,
            expected_concepts=list(question.expected_concepts),
            user_answer=user_answer,
            topic_name=topic.name,
        )
    except ValueError as e:
        logger.error(f"LLM configuration error: {e}")
        raise LLMServiceUnavailableError(
            "Question grading service is temporarily unavailable"
        )
    except GeminiServiceUnavailable as e:
        logger.warning(f"Gemini service unavailable: {e}")
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

    await log_activity(
        db=db,
        user_id=user_id,
        activity_type=ActivityType.QUESTION_ATTEMPT,
        reference_id=question_id,
    )

    # Extract phase from topic_id (e.g., "phase1-topic4" -> "phase1")
    phase = topic_id.split("-")[0] if "-" in topic_id else "unknown"
    if grade_result.is_passed:
        log_metric("questions.passed", 1, {"phase": phase, "topic_id": topic_id})
        # Invalidate cache so dashboard/progress refreshes immediately
        invalidate_progress_cache(user_id)
    else:
        log_metric("questions.failed", 1, {"phase": phase, "topic_id": topic_id})

    # Calculate attempts_used and lockout_until: failures + this attempt (if failed)
    attempts_used = None
    lockout_until = None
    if not grade_result.is_passed and not already_passed:
        attempts_used = failed_attempts_before + 1
        # If user just hit max attempts, calculate when lockout expires
        if attempts_used >= settings.quiz_max_attempts:
            lockout_until = datetime.now(UTC) + timedelta(
                minutes=settings.quiz_lockout_minutes
            )

    return QuestionGradeResult(
        question_id=question_id,
        is_passed=grade_result.is_passed,
        feedback=grade_result.feedback,
        confidence_score=grade_result.confidence_score,
        attempt_id=attempt.id,
        attempts_used=attempts_used,
        lockout_until=lockout_until,
    )
