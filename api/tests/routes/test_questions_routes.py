"""Tests for questions routes."""

from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, patch

import pytest
from httpx import AsyncClient

from services.questions_service import (
    LLMGradingError,
    LLMServiceUnavailableError,
    QuestionAttemptLimitExceeded,
)

# Mark all tests in this module as integration tests (database required)
pytestmark = pytest.mark.integration


def _get_valid_question():
    """Get a valid question from content for testing."""
    from services.content_service import get_all_phases

    phases = get_all_phases()
    for phase in phases:
        for topic in phase.topics:
            for question in topic.questions:
                if question.expected_concepts:
                    return topic.id, question.id
    return None, None


class TestSubmitQuestionAnswer:
    """Tests for POST /api/questions/submit endpoint."""

    @patch("services.questions_service.grade_answer")
    async def test_successful_submission_passing(
        self, mock_grade, authenticated_client: AsyncClient
    ):
        """Test successful question submission that passes."""
        topic_id, question_id = _get_valid_question()
        if not question_id:
            pytest.skip("No questions with expected_concepts in content")

        mock_grade.return_value = AsyncMock(
            is_passed=True,
            feedback="Great answer!",
            confidence_score=0.9,
        )

        response = await authenticated_client.post(
            "/api/questions/submit",
            json={
                "topic_id": topic_id,
                "question_id": question_id,
                "user_answer": "A comprehensive answer about cloud computing",
            },
        )

        assert response.status_code == 200
        data = response.json()
        assert data["question_id"] == question_id
        assert data["is_passed"] is True
        assert "llm_feedback" in data

    @patch("services.questions_service.grade_answer")
    async def test_successful_submission_failing(
        self, mock_grade, authenticated_client: AsyncClient
    ):
        """Test successful question submission that fails grading."""
        topic_id, question_id = _get_valid_question()
        if not question_id:
            pytest.skip("No questions with expected_concepts in content")

        mock_grade.return_value = AsyncMock(
            is_passed=False,
            feedback="Missing key concepts",
            confidence_score=0.3,
        )

        response = await authenticated_client.post(
            "/api/questions/submit",
            json={
                "topic_id": topic_id,
                "question_id": question_id,
                "user_answer": "Incomplete answer",
            },
        )

        assert response.status_code == 200
        data = response.json()
        assert data["is_passed"] is False

    async def test_returns_404_for_unknown_topic(
        self, authenticated_client: AsyncClient
    ):
        """Test returns 404 for unknown topic ID (valid format, doesn't exist)."""
        response = await authenticated_client.post(
            "/api/questions/submit",
            json={
                "topic_id": "phase999-topic999",
                "question_id": "phase999-topic999-q1",
                "user_answer": "My answer is at least 10 characters long",
            },
        )

        assert response.status_code == 404

    async def test_returns_404_for_unknown_question(
        self, authenticated_client: AsyncClient
    ):
        """Test returns 404 for unknown question ID (valid format, doesn't exist)."""
        from services.content_service import get_all_phases

        phases = get_all_phases()
        if not phases or not phases[0].topics:
            pytest.skip("No topics in content")

        topic = phases[0].topics[0]

        response = await authenticated_client.post(
            "/api/questions/submit",
            json={
                "topic_id": topic.id,
                "question_id": f"{topic.id}-q999",
                "user_answer": "My answer is at least 10 characters long",
            },
        )

        assert response.status_code == 404

    @patch("routes.questions_routes.submit_question_answer")
    async def test_returns_429_when_locked_out(
        self, mock_submit, authenticated_client: AsyncClient
    ):
        """Test returns 429 when user is locked out from too many attempts."""
        topic_id, question_id = _get_valid_question()
        if not question_id:
            pytest.skip("No questions with expected_concepts in content")

        lockout_until = datetime.now(UTC) + timedelta(minutes=5)
        mock_submit.side_effect = QuestionAttemptLimitExceeded(
            lockout_until=lockout_until,
            attempts_used=3,
        )

        response = await authenticated_client.post(
            "/api/questions/submit",
            json={
                "topic_id": topic_id,
                "question_id": question_id,
                "user_answer": "Short answer",
            },
        )

        assert response.status_code == 429
        data = response.json()
        assert data["attempts_used"] == 3
        assert data["lockout_until"] == lockout_until.isoformat()
        assert response.headers.get("Retry-After") is not None

    @patch("routes.questions_routes.submit_question_answer")
    async def test_returns_503_when_llm_unavailable(
        self, mock_submit, authenticated_client: AsyncClient
    ):
        """Test returns 503 when LLM service is unavailable."""
        topic_id, question_id = _get_valid_question()
        if not question_id:
            pytest.skip("No questions with expected_concepts in content")

        mock_submit.side_effect = LLMServiceUnavailableError()

        response = await authenticated_client.post(
            "/api/questions/submit",
            json={
                "topic_id": topic_id,
                "question_id": question_id,
                "user_answer": "My answer is at least 10 characters long",
            },
        )

        assert response.status_code == 503
        data = response.json()
        assert data["detail"] == "Question grading service is temporarily unavailable"

    @patch("routes.questions_routes.submit_question_answer")
    async def test_returns_500_when_llm_grading_fails(
        self, mock_submit, authenticated_client: AsyncClient
    ):
        """Test returns 500 when LLM grading fails unexpectedly."""
        topic_id, question_id = _get_valid_question()
        if not question_id:
            pytest.skip("No questions with expected_concepts in content")

        mock_submit.side_effect = LLMGradingError()

        response = await authenticated_client.post(
            "/api/questions/submit",
            json={
                "topic_id": topic_id,
                "question_id": question_id,
                "user_answer": "My answer is at least 10 characters long",
            },
        )

        assert response.status_code == 500
        data = response.json()
        assert data["detail"] == "Failed to grade your answer. Please try again."

    async def test_returns_401_for_unauthenticated(
        self, unauthenticated_client: AsyncClient
    ):
        """Test returns 401 for unauthenticated request."""
        response = await unauthenticated_client.post(
            "/api/questions/submit",
            json={
                "topic_id": "phase0-topic1",
                "question_id": "phase0-topic1-q1",
                "user_answer": "My answer",
            },
        )

        assert response.status_code == 401

    async def test_returns_422_for_missing_fields(
        self, authenticated_client: AsyncClient
    ):
        """Test returns 422 for missing required fields."""
        response = await authenticated_client.post(
            "/api/questions/submit",
            json={"topic_id": "phase0-topic1"},  # Missing question_id and user_answer
        )

        assert response.status_code == 422
