"""Tests for questions service."""

from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

# Mark all tests in this module as integration tests (database required)
pytestmark = pytest.mark.integration

from services.questions_service import (
    GradingConceptsNotFoundError,
    LLMGradingError,
    LLMServiceUnavailableError,
    QuestionAttemptLimitExceeded,
    QuestionUnknownQuestionError,
    QuestionUnknownTopicError,
    submit_question_answer,
)
from tests.factories import UserFactory


class TestSubmitQuestionAnswer:
    """Tests for submit_question_answer."""

    @pytest.fixture
    async def user(self, db_session: AsyncSession):
        """Create a test user."""
        user = UserFactory.build()
        db_session.add(user)
        await db_session.flush()
        return user

    @pytest.fixture
    def mock_grade_answer(self):
        """Mock the LLM grade_answer function."""
        with patch("services.questions_service.grade_answer") as mock:
            mock.return_value = AsyncMock(
                is_passed=True,
                feedback="Great answer!",
                confidence_score=0.95,
            )
            yield mock

    def _get_test_question(self):
        """Get a real question from content for testing."""
        from services.content_service import get_all_phases

        phases = get_all_phases()
        for phase in phases:
            for topic in phase.topics:
                for question in topic.questions:
                    if question.expected_concepts:
                        return topic.id, question.id, question
        return None, None, None

    async def test_raises_for_unknown_topic(self, db_session: AsyncSession, user):
        """Test that unknown topic ID raises QuestionUnknownTopicError."""
        with pytest.raises(QuestionUnknownTopicError):
            await submit_question_answer(
                db_session,
                user.id,
                "nonexistent-topic",
                "q1",
                "my answer",
            )

    async def test_raises_for_unknown_question(self, db_session: AsyncSession, user):
        """Test that unknown question ID raises QuestionUnknownQuestionError."""
        from services.content_service import get_all_phases

        phases = get_all_phases()
        if not phases or not phases[0].topics:
            pytest.skip("No phases/topics available in content")

        topic = phases[0].topics[0]

        with pytest.raises(QuestionUnknownQuestionError):
            await submit_question_answer(
                db_session,
                user.id,
                topic.id,
                "nonexistent-question-id",
                "my answer",
            )

    async def test_raises_for_missing_grading_concepts(
        self, db_session: AsyncSession, user
    ):
        """Test that missing grading concepts raises GradingConceptsNotFoundError."""
        from services.content_service import get_all_phases

        phases = get_all_phases()
        # Find a question without expected_concepts (if any)
        for phase in phases:
            for topic in phase.topics:
                for question in topic.questions:
                    if not question.expected_concepts:
                        with pytest.raises(GradingConceptsNotFoundError):
                            await submit_question_answer(
                                db_session,
                                user.id,
                                topic.id,
                                question.id,
                                "my answer",
                            )
                        return

        pytest.skip("All questions have expected_concepts")

    async def test_successful_submission_passing(
        self, db_session: AsyncSession, user, mock_grade_answer
    ):
        """Test successful question submission that passes."""
        topic_id, question_id, question = self._get_test_question()
        if not question_id:
            pytest.skip("No questions with expected_concepts in content")

        mock_grade_answer.return_value = AsyncMock(
            is_passed=True,
            feedback="Excellent!",
            confidence_score=0.9,
        )

        result = await submit_question_answer(
            db_session,
            user.id,
            topic_id,
            question_id,
            "A comprehensive answer",
        )

        assert result.question_id == question_id
        assert result.is_passed is True
        assert result.feedback == "Excellent!"
        assert result.attempt_id is not None

    async def test_successful_submission_failing(
        self, db_session: AsyncSession, user, mock_grade_answer
    ):
        """Test successful question submission that fails grading."""
        topic_id, question_id, question = self._get_test_question()
        if not question_id:
            pytest.skip("No questions with expected_concepts in content")

        mock_grade_answer.return_value = AsyncMock(
            is_passed=False,
            feedback="Missing key concepts",
            confidence_score=0.3,
        )

        result = await submit_question_answer(
            db_session,
            user.id,
            topic_id,
            question_id,
            "Incomplete answer",
        )

        assert result.is_passed is False
        assert result.attempts_used == 1

    async def test_attempt_limiting_enforced(
        self, db_session: AsyncSession, user, mock_grade_answer
    ):
        """Test that attempt limiting is enforced."""
        topic_id, question_id, question = self._get_test_question()
        if not question_id:
            pytest.skip("No questions with expected_concepts in content")

        mock_grade_answer.return_value = AsyncMock(
            is_passed=False,
            feedback="Wrong",
            confidence_score=0.2,
        )

        # Make max_attempts (3) failures
        from core.config import get_settings

        settings = get_settings()

        for _ in range(settings.quiz_max_attempts):
            await submit_question_answer(
                db_session,
                user.id,
                topic_id,
                question_id,
                "Wrong answer",
            )

        # Next attempt should be locked out
        with pytest.raises(QuestionAttemptLimitExceeded) as exc_info:
            await submit_question_answer(
                db_session,
                user.id,
                topic_id,
                question_id,
                "Another attempt",
            )

        assert exc_info.value.lockout_until is not None
        assert exc_info.value.attempts_used >= settings.quiz_max_attempts

    async def test_already_passed_exempt_from_lockout(
        self, db_session: AsyncSession, user, mock_grade_answer
    ):
        """Test that users who already passed can re-practice without lockout."""
        topic_id, question_id, question = self._get_test_question()
        if not question_id:
            pytest.skip("No questions with expected_concepts in content")

        # First, pass the question
        mock_grade_answer.return_value = AsyncMock(
            is_passed=True,
            feedback="Correct!",
            confidence_score=0.95,
        )
        await submit_question_answer(
            db_session,
            user.id,
            topic_id,
            question_id,
            "Correct answer",
        )

        # Now fail multiple times - should not be locked out
        mock_grade_answer.return_value = AsyncMock(
            is_passed=False,
            feedback="Wrong",
            confidence_score=0.2,
        )

        from core.config import get_settings

        settings = get_settings()

        for _ in range(settings.quiz_max_attempts + 1):
            # Should not raise QuestionAttemptLimitExceeded
            result = await submit_question_answer(
                db_session,
                user.id,
                topic_id,
                question_id,
                "Wrong answer",
            )
            assert result is not None

    async def test_llm_service_unavailable(
        self, db_session: AsyncSession, user, mock_grade_answer
    ):
        """Test handling of LLM service being unavailable."""
        topic_id, question_id, question = self._get_test_question()
        if not question_id:
            pytest.skip("No questions with expected_concepts in content")

        mock_grade_answer.side_effect = ValueError("API key not configured")

        with pytest.raises(LLMServiceUnavailableError):
            await submit_question_answer(
                db_session,
                user.id,
                topic_id,
                question_id,
                "My answer",
            )

    async def test_llm_grading_error(
        self, db_session: AsyncSession, user, mock_grade_answer
    ):
        """Test handling of LLM grading failure."""
        topic_id, question_id, question = self._get_test_question()
        if not question_id:
            pytest.skip("No questions with expected_concepts in content")

        mock_grade_answer.side_effect = Exception("Random error")

        with pytest.raises(LLMGradingError):
            await submit_question_answer(
                db_session,
                user.id,
                topic_id,
                question_id,
                "My answer",
            )


class TestQuestionAttemptLimitExceeded:
    """Tests for QuestionAttemptLimitExceeded exception."""

    def test_exception_attributes(self):
        """Test that exception has correct attributes."""
        lockout_until = datetime.now(UTC) + timedelta(hours=1)
        exc = QuestionAttemptLimitExceeded(lockout_until, 3)

        assert exc.lockout_until == lockout_until
        assert exc.attempts_used == 3
        assert "Try again after" in str(exc)
