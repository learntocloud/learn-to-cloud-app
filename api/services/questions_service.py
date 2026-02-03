"""Questions service for knowledge check grading and progress tracking.

This module handles:
- Question submission and grading via LLM
- Scenario question generation for varied assessments
- Recording question attempts with activity logging
- Attempt limiting with lockout periods

Routes should delegate question business logic to this module.

Grading rubrics and scenario seeds are embedded in the content JSON files
alongside question prompts. This simplifies the architecture by keeping all
content in one place (frontend/public/content/).
"""

from datetime import UTC, datetime, timedelta

from sqlalchemy.ext.asyncio import AsyncSession

from core import get_logger
from core.cache import invalidate_progress_cache
from core.config import get_settings
from core.telemetry import add_custom_attribute, log_metric, track_operation
from core.wide_event import set_wide_event_field, set_wide_event_fields
from models import ActivityType
from repositories.progress_repository import (
    QuestionAttemptRepository,
    UserPhaseProgressRepository,
)
from repositories.scenario_repository import ScenarioRepository
from schemas import QuestionGradeResult, ScenarioQuestionResponse
from services.activity_service import log_activity
from services.content_service import get_topic_by_id
from services.llm_service import (
    GeminiServiceUnavailable,
    ScenarioGenerationFailed,
    generate_scenario_question,
    grade_answer,
)

logger = get_logger(__name__)


class LLMServiceUnavailableError(Exception):
    """Raised when LLM service is not configured or unavailable."""


class LLMGradingError(Exception):
    """Raised when LLM grading fails."""


class ScenarioUnavailableError(Exception):
    """Raised when scenario generation is unavailable.

    This results in a user-friendly error message instead of falling back
    to base questions, which would defeat scenario-based assessment.
    """


class QuestionValidationError(Exception):
    """Raised when question submission validation fails."""


class QuestionUnknownTopicError(QuestionValidationError):
    """Raised when a topic_id doesn't exist in content."""


class QuestionUnknownQuestionError(QuestionValidationError):
    """Raised when a question_id doesn't exist in the given topic."""


class GradingConceptsNotFoundError(QuestionValidationError):
    """Raised when grading concepts are not found for a question."""


class ScenarioGenerationError(Exception):
    """Raised when scenario generation fails and fallback is not available."""


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


def _parse_phase_id_from_topic_id(topic_id: str) -> int | None:
    if not isinstance(topic_id, str) or not topic_id.startswith("phase"):
        return None
    try:
        return int(topic_id.split("-")[0].replace("phase", ""))
    except (ValueError, IndexError):
        return None


@track_operation("get_scenario_question")
async def get_scenario_question(
    db: AsyncSession,
    user_id: str,
    topic_id: str,
    question_id: str,
) -> ScenarioQuestionResponse:
    """Get a scenario-wrapped question for a user.

    Checks cache first, generates new scenario if not cached.
    Falls back to base prompt if generation fails.

    Args:
        topic_id: Topic ID (e.g., "phase1-topic4")
        question_id: Question ID (e.g., "phase1-topic4-q1")

    Raises:
        QuestionUnknownTopicError: If topic_id doesn't exist in content
        QuestionUnknownQuestionError: If question_id doesn't exist in topic
        QuestionAttemptLimitExceeded: If user is locked out
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

    # Check if user is locked out before generating scenario
    already_passed = await question_repo.has_passed_question(user_id, question_id)
    if not already_passed:
        lockout_window_start = datetime.now(UTC) - timedelta(
            minutes=settings.quiz_lockout_minutes
        )
        failed_attempts = await question_repo.count_recent_failed_attempts(
            user_id=user_id,
            question_id=question_id,
            since=lockout_window_start,
        )
        if failed_attempts >= settings.quiz_max_attempts:
            oldest_failure = await question_repo.get_oldest_recent_failure(
                user_id=user_id,
                question_id=question_id,
                since=lockout_window_start,
            )
            lockout_until = (oldest_failure or datetime.now(UTC)) + timedelta(
                minutes=settings.quiz_lockout_minutes
            )
            raise QuestionAttemptLimitExceeded(
                lockout_until=lockout_until,
                attempts_used=failed_attempts,
            )

    # Check database for cached scenario (survives container restarts)
    scenario_repo = ScenarioRepository(db)
    cached_scenario = await scenario_repo.get(user_id, question_id)
    if cached_scenario:
        set_wide_event_field("scenario_cache_hit", True)
        log_metric("scenario.cache_hit", 1, {"topic_id": topic_id})
        return ScenarioQuestionResponse(
            question_id=question_id,
            scenario_prompt=cached_scenario,
            base_prompt=question.prompt,
        )

    # Require scenario seeds - no fallback to base question
    if not question.scenario_seeds:
        set_wide_event_fields(
            scenario_error="no_seeds_configured",
            question_id=question_id,
        )
        logger.error(
            "scenario.no_seeds_configured",
            topic_id=topic_id,
            question_id=question_id,
        )
        raise ScenarioUnavailableError(
            "This question is not yet configured for scenario-based assessment. "
            "Please contact support."
        )

    # Generate scenario - raises ScenarioGenerationFailed on error
    try:
        result = await generate_scenario_question(
            base_prompt=question.prompt,
            scenario_seeds=list(question.scenario_seeds),
            topic_name=topic.name,
        )
    except ScenarioGenerationFailed as e:
        logger.error(
            "scenario.generation.failed",
            topic_id=topic_id,
            question_id=question_id,
            reason=e.reason,
        )
        raise ScenarioUnavailableError(
            "Scenario generation is temporarily unavailable. "
            "Please try again in a few minutes."
        ) from e

    # Persist the generated scenario to database
    await scenario_repo.upsert(user_id, question_id, result.scenario_prompt)

    return ScenarioQuestionResponse(
        question_id=question_id,
        scenario_prompt=result.scenario_prompt,
        base_prompt=question.prompt,
    )


@track_operation("question_submission")
async def submit_question_answer(
    db: AsyncSession,
    user_id: str,
    topic_id: str,
    question_id: str,
    user_answer: str,
    scenario_context: str | None = None,
) -> QuestionGradeResult:
    """Submit an answer for LLM grading and record the attempt.

    Args:
        topic_id: Topic ID (e.g., "phase1-topic4")
        question_id: Question ID (e.g., "phase1-topic4-q1")
        user_answer: The user's answer text
        scenario_context: Optional scenario-wrapped question (from GET /scenario)

    Raises:
        QuestionUnknownTopicError: If topic_id doesn't exist in content
        QuestionUnknownQuestionError: If question_id doesn't exist in topic
        GradingConceptsNotFoundError: If grading rubric/concepts not configured
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

    # Require grading rubric or concepts for evaluation
    if not question.grading_rubric and not question.concepts:
        set_wide_event_fields(
            question_error="grading_config_not_found",
            question_id=question_id,
        )
        raise GradingConceptsNotFoundError(
            f"Grading configuration not found for question: {question_id}"
        )

    already_passed = await question_repo.has_passed_question(user_id, question_id)
    failed_attempts_before = 0
    if not already_passed:
        lockout_window_start = datetime.now(UTC) - timedelta(
            minutes=settings.quiz_lockout_minutes
        )
        failed_attempts_before = await question_repo.count_recent_failed_attempts(
            user_id=user_id,
            question_id=question_id,
            since=lockout_window_start,
        )
        if failed_attempts_before >= settings.quiz_max_attempts:
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
            user_answer=user_answer,
            topic_name=topic.name,
            grading_rubric=question.grading_rubric,
            concepts=question.concepts,
            scenario_context=scenario_context,
        )
    except ValueError as e:
        set_wide_event_fields(llm_error="config_error", llm_error_detail=str(e))
        raise LLMServiceUnavailableError(
            "Question grading service is temporarily unavailable"
        )
    except GeminiServiceUnavailable as e:
        set_wide_event_fields(llm_error="service_unavailable", llm_error_detail=str(e))
        raise LLMServiceUnavailableError(
            "Question grading service is temporarily unavailable"
        )
    except Exception as e:
        set_wide_event_fields(llm_error="grading_failed", llm_error_detail=str(e))
        raise LLMGradingError("Failed to grade your answer. Please try again.") from e

    attempt = await question_repo.create(
        user_id=user_id,
        topic_id=topic_id,
        question_id=question_id,
        is_passed=grade_result.is_passed,
        user_answer=user_answer,
        scenario_prompt=scenario_context,
        llm_feedback=grade_result.feedback,
        confidence_score=grade_result.confidence_score,
    )

    await log_activity(
        db=db,
        user_id=user_id,
        activity_type=ActivityType.QUESTION_ATTEMPT,
        reference_id=question_id,
    )

    phase = topic_id.split("-")[0] if "-" in topic_id else "unknown"
    if grade_result.is_passed:
        log_metric("questions.passed", 1, {"phase": phase, "topic_id": topic_id})
        invalidate_progress_cache(user_id)
        if not already_passed:
            phase_id = _parse_phase_id_from_topic_id(topic_id)
            if phase_id is not None:
                summary_repo = UserPhaseProgressRepository(db)
                await summary_repo.apply_delta(user_id, phase_id, questions_delta=1)
        # Delete persisted scenario so user gets fresh one if they retry
        scenario_repo = ScenarioRepository(db)
        await scenario_repo.delete(user_id, question_id)
    else:
        log_metric("questions.failed", 1, {"phase": phase, "topic_id": topic_id})

    attempts_used = None
    lockout_until = None
    if not grade_result.is_passed and not already_passed:
        attempts_used = failed_attempts_before + 1
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
