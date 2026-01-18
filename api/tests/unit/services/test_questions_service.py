"""Tests for services/questions_service.py - question grading and progress tracking."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from services.questions_service import (
    LLMGradingError,
    LLMServiceUnavailableError,
    QuestionGradeResult,
    QuestionUnknownQuestionError,
    QuestionUnknownTopicError,
    submit_question_answer,
)


class TestQuestionGradeResultDataclass:
    """Test QuestionGradeResult dataclass."""

    def test_grade_result_fields(self):
        """QuestionGradeResult has expected fields."""
        result = QuestionGradeResult(
            question_id="phase1-topic1-q1",
            is_passed=True,
            feedback="Great answer!",
            confidence_score=0.95,
            attempt_id=123,
        )
        assert result.question_id == "phase1-topic1-q1"
        assert result.is_passed is True
        assert result.confidence_score == 0.95
        assert result.attempt_id == 123


class TestExceptions:
    """Test custom exceptions."""

    def test_llm_service_unavailable_error(self):
        """LLMServiceUnavailableError can be raised."""
        with pytest.raises(LLMServiceUnavailableError, match="unavailable"):
            raise LLMServiceUnavailableError("Service unavailable")

    def test_llm_grading_error(self):
        """LLMGradingError can be raised."""
        with pytest.raises(LLMGradingError, match="[Gg]rading"):
            raise LLMGradingError("Grading failed")

    def test_question_unknown_topic_error(self):
        """QuestionUnknownTopicError can be raised."""
        with pytest.raises(QuestionUnknownTopicError, match="topic"):
            raise QuestionUnknownTopicError("Unknown topic_id")

    def test_question_unknown_question_error(self):
        """QuestionUnknownQuestionError can be raised."""
        with pytest.raises(QuestionUnknownQuestionError, match="question"):
            raise QuestionUnknownQuestionError("Unknown question_id")


class TestSubmitQuestionAnswer:
    """Tests for submit_question_answer function."""

    @pytest.fixture
    def mock_topic(self):
        """Create a mock topic with questions including expected_concepts."""
        mock_question = MagicMock()
        mock_question.id = "phase1-topic1-q1"
        mock_question.prompt = "What is cloud computing?"
        # expected_concepts now embedded in content (not from database)
        mock_question.expected_concepts = ("iaas", "paas", "saas")

        mock_topic = MagicMock()
        mock_topic.id = "phase1-topic1"
        mock_topic.name = "Cloud Basics"
        mock_topic.questions = [mock_question]
        return mock_topic

    @pytest.fixture
    def mock_grade_result(self):
        """Create a mock LLM grade result."""
        result = MagicMock()
        result.is_passed = True
        result.feedback = "Great answer! You covered all concepts."
        result.confidence_score = 0.92
        return result

    @pytest.mark.asyncio
    async def test_unknown_topic_raises_error(self):
        """Submitting to unknown topic raises QuestionUnknownTopicError."""
        mock_db = MagicMock()

        with patch("services.questions_service.get_topic_by_id", return_value=None):
            with pytest.raises(QuestionUnknownTopicError, match="Unknown topic_id"):
                await submit_question_answer(
                    mock_db,
                    "user-123",
                    "nonexistent-topic",
                    "q1",
                    "my answer",
                )

    @pytest.mark.asyncio
    async def test_unknown_question_raises_error(self, mock_topic):
        """Submitting to unknown question raises QuestionUnknownQuestionError."""
        mock_db = MagicMock()

        with patch(
            "services.questions_service.get_topic_by_id", return_value=mock_topic
        ):
            with pytest.raises(
                QuestionUnknownQuestionError, match="Unknown question_id"
            ):
                await submit_question_answer(
                    mock_db,
                    "user-123",
                    "phase1-topic1",
                    "nonexistent-question",
                    "my answer",
                )

    @pytest.mark.asyncio
    async def test_llm_config_error_raises_unavailable(self, mock_topic):
        """LLM configuration error raises LLMServiceUnavailableError."""
        mock_db = MagicMock()

        with (
            patch(
                "services.questions_service.get_topic_by_id", return_value=mock_topic
            ),
            patch(
                "services.questions_service.grade_answer",
                side_effect=ValueError("No API key"),
            ),
        ):
            with pytest.raises(LLMServiceUnavailableError, match="unavailable"):
                await submit_question_answer(
                    mock_db,
                    "user-123",
                    "phase1-topic1",
                    "phase1-topic1-q1",
                    "my answer",
                )

    @pytest.mark.asyncio
    async def test_llm_generic_error_raises_grading_error(self, mock_topic):
        """Generic LLM error raises LLMGradingError."""
        mock_db = MagicMock()

        with (
            patch(
                "services.questions_service.get_topic_by_id", return_value=mock_topic
            ),
            patch(
                "services.questions_service.grade_answer",
                side_effect=RuntimeError("API timeout"),
            ),
        ):
            with pytest.raises(LLMGradingError, match="Failed to grade"):
                await submit_question_answer(
                    mock_db,
                    "user-123",
                    "phase1-topic1",
                    "phase1-topic1-q1",
                    "my answer",
                )

    @pytest.mark.asyncio
    async def test_successful_submission_passed(self, mock_topic, mock_grade_result):
        """Successful submission returns QuestionGradeResult."""
        mock_db = MagicMock()
        mock_question_repo = AsyncMock()
        mock_activity_repo = AsyncMock()

        mock_attempt = MagicMock()
        mock_attempt.id = 456
        mock_question_repo.create.return_value = mock_attempt

        with (
            patch(
                "services.questions_service.get_topic_by_id", return_value=mock_topic
            ),
            patch(
                "services.questions_service.grade_answer",
                return_value=mock_grade_result,
            ),
            patch(
                "services.questions_service.QuestionAttemptRepository",
                return_value=mock_question_repo,
            ),
            patch(
                "services.questions_service.ActivityRepository",
                return_value=mock_activity_repo,
            ),
            patch("services.questions_service.invalidate_progress_cache"),
            patch("services.questions_service.log_metric"),
            patch("services.questions_service.add_custom_attribute"),
        ):
            answer = (
                "Cloud computing provides on-demand resources "
                "including IaaS, PaaS, and SaaS."
            )
            result = await submit_question_answer(
                mock_db,
                "user-123",
                "phase1-topic1",
                "phase1-topic1-q1",
                answer,
            )

        assert result.question_id == "phase1-topic1-q1"
        assert result.is_passed is True
        assert result.feedback == "Great answer! You covered all concepts."
        assert result.confidence_score == 0.92
        assert result.attempt_id == 456

    @pytest.mark.asyncio
    async def test_submission_creates_attempt_record(
        self, mock_topic, mock_grade_result
    ):
        """Submission creates a question attempt record."""
        mock_db = MagicMock()
        mock_question_repo = AsyncMock()
        mock_activity_repo = AsyncMock()

        mock_attempt = MagicMock()
        mock_attempt.id = 789
        mock_question_repo.create.return_value = mock_attempt

        with (
            patch(
                "services.questions_service.get_topic_by_id", return_value=mock_topic
            ),
            patch(
                "services.questions_service.grade_answer",
                return_value=mock_grade_result,
            ),
            patch(
                "services.questions_service.QuestionAttemptRepository",
                return_value=mock_question_repo,
            ),
            patch(
                "services.questions_service.ActivityRepository",
                return_value=mock_activity_repo,
            ),
            patch("services.questions_service.invalidate_progress_cache"),
            patch("services.questions_service.log_metric"),
            patch("services.questions_service.add_custom_attribute"),
        ):
            await submit_question_answer(
                mock_db,
                "user-123",
                "phase1-topic1",
                "phase1-topic1-q1",
                "My answer text",
            )

        mock_question_repo.create.assert_called_once_with(
            user_id="user-123",
            topic_id="phase1-topic1",
            question_id="phase1-topic1-q1",
            is_passed=True,
            user_answer="My answer text",
            llm_feedback="Great answer! You covered all concepts.",
            confidence_score=0.92,
        )

    @pytest.mark.asyncio
    async def test_submission_logs_activity(self, mock_topic, mock_grade_result):
        """Submission logs activity for streak tracking."""
        mock_db = MagicMock()
        mock_question_repo = AsyncMock()
        mock_activity_repo = AsyncMock()

        mock_attempt = MagicMock()
        mock_attempt.id = 1
        mock_question_repo.create.return_value = mock_attempt

        from models import ActivityType

        with (
            patch(
                "services.questions_service.get_topic_by_id", return_value=mock_topic
            ),
            patch(
                "services.questions_service.grade_answer",
                return_value=mock_grade_result,
            ),
            patch(
                "services.questions_service.QuestionAttemptRepository",
                return_value=mock_question_repo,
            ),
            patch(
                "services.questions_service.ActivityRepository",
                return_value=mock_activity_repo,
            ),
            patch("services.questions_service.invalidate_progress_cache"),
            patch("services.questions_service.log_metric"),
            patch("services.questions_service.add_custom_attribute"),
        ):
            await submit_question_answer(
                mock_db,
                "user-123",
                "phase1-topic1",
                "phase1-topic1-q1",
                "My answer",
            )

        mock_activity_repo.log_activity.assert_called_once()
        call_kwargs = mock_activity_repo.log_activity.call_args.kwargs
        assert call_kwargs["user_id"] == "user-123"
        assert call_kwargs["activity_type"] == ActivityType.QUESTION_ATTEMPT
        assert call_kwargs["reference_id"] == "phase1-topic1-q1"

    @pytest.mark.asyncio
    async def test_passed_answer_invalidates_cache(self, mock_topic, mock_grade_result):
        """Passed answer invalidates progress cache."""
        mock_db = MagicMock()
        mock_question_repo = AsyncMock()
        mock_activity_repo = AsyncMock()

        mock_attempt = MagicMock()
        mock_attempt.id = 1
        mock_question_repo.create.return_value = mock_attempt

        mock_invalidate = MagicMock()

        with (
            patch(
                "services.questions_service.get_topic_by_id", return_value=mock_topic
            ),
            patch(
                "services.questions_service.grade_answer",
                return_value=mock_grade_result,
            ),
            patch(
                "services.questions_service.QuestionAttemptRepository",
                return_value=mock_question_repo,
            ),
            patch(
                "services.questions_service.ActivityRepository",
                return_value=mock_activity_repo,
            ),
            patch(
                "services.questions_service.invalidate_progress_cache",
                mock_invalidate,
            ),
            patch("services.questions_service.log_metric"),
            patch("services.questions_service.add_custom_attribute"),
        ):
            await submit_question_answer(
                mock_db,
                "user-123",
                "phase1-topic1",
                "phase1-topic1-q1",
                "My answer",
            )

        mock_invalidate.assert_called_once_with("user-123")

    @pytest.mark.asyncio
    async def test_failed_answer_does_not_invalidate_cache(self, mock_topic):
        """Failed answer does not invalidate progress cache."""
        mock_db = MagicMock()
        mock_question_repo = AsyncMock()
        mock_activity_repo = AsyncMock()

        mock_attempt = MagicMock()
        mock_attempt.id = 1
        mock_question_repo.create.return_value = mock_attempt

        mock_grade_result = MagicMock()
        mock_grade_result.is_passed = False
        mock_grade_result.feedback = "Try again"
        mock_grade_result.confidence_score = 0.3

        mock_invalidate = MagicMock()

        with (
            patch(
                "services.questions_service.get_topic_by_id", return_value=mock_topic
            ),
            patch(
                "services.questions_service.grade_answer",
                return_value=mock_grade_result,
            ),
            patch(
                "services.questions_service.QuestionAttemptRepository",
                return_value=mock_question_repo,
            ),
            patch(
                "services.questions_service.ActivityRepository",
                return_value=mock_activity_repo,
            ),
            patch(
                "services.questions_service.invalidate_progress_cache",
                mock_invalidate,
            ),
            patch("services.questions_service.log_metric"),
            patch("services.questions_service.add_custom_attribute"),
        ):
            await submit_question_answer(
                mock_db,
                "user-123",
                "phase1-topic1",
                "phase1-topic1-q1",
                "Wrong answer",
            )

        mock_invalidate.assert_not_called()

    @pytest.mark.asyncio
    async def test_logs_metrics_for_passed(self, mock_topic, mock_grade_result):
        """Logs questions.passed metric when answer passes."""
        mock_db = MagicMock()
        mock_question_repo = AsyncMock()
        mock_activity_repo = AsyncMock()

        mock_attempt = MagicMock()
        mock_attempt.id = 1
        mock_question_repo.create.return_value = mock_attempt

        mock_log_metric = MagicMock()

        with (
            patch(
                "services.questions_service.get_topic_by_id", return_value=mock_topic
            ),
            patch(
                "services.questions_service.grade_answer",
                return_value=mock_grade_result,
            ),
            patch(
                "services.questions_service.QuestionAttemptRepository",
                return_value=mock_question_repo,
            ),
            patch(
                "services.questions_service.ActivityRepository",
                return_value=mock_activity_repo,
            ),
            patch("services.questions_service.invalidate_progress_cache"),
            patch("services.questions_service.log_metric", mock_log_metric),
            patch("services.questions_service.add_custom_attribute"),
        ):
            await submit_question_answer(
                mock_db,
                "user-123",
                "phase1-topic1",
                "phase1-topic1-q1",
                "My answer",
            )

        mock_log_metric.assert_called_once_with(
            "questions.passed",
            1,
            {"phase": "phase1", "topic_id": "phase1-topic1"},
        )

    @pytest.mark.asyncio
    async def test_logs_metrics_for_failed(self, mock_topic):
        """Logs questions.failed metric when answer fails."""
        mock_db = MagicMock()
        mock_question_repo = AsyncMock()
        mock_activity_repo = AsyncMock()

        mock_attempt = MagicMock()
        mock_attempt.id = 1
        mock_question_repo.create.return_value = mock_attempt

        mock_grade_result = MagicMock()
        mock_grade_result.is_passed = False
        mock_grade_result.feedback = "Try again"
        mock_grade_result.confidence_score = 0.3

        mock_log_metric = MagicMock()

        with (
            patch(
                "services.questions_service.get_topic_by_id", return_value=mock_topic
            ),
            patch(
                "services.questions_service.grade_answer",
                return_value=mock_grade_result,
            ),
            patch(
                "services.questions_service.QuestionAttemptRepository",
                return_value=mock_question_repo,
            ),
            patch(
                "services.questions_service.ActivityRepository",
                return_value=mock_activity_repo,
            ),
            patch("services.questions_service.invalidate_progress_cache"),
            patch("services.questions_service.log_metric", mock_log_metric),
            patch("services.questions_service.add_custom_attribute"),
        ):
            await submit_question_answer(
                mock_db,
                "user-123",
                "phase1-topic1",
                "phase1-topic1-q1",
                "Wrong answer",
            )

        mock_log_metric.assert_called_once_with(
            "questions.failed",
            1,
            {"phase": "phase1", "topic_id": "phase1-topic1"},
        )
