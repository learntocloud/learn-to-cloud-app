"""Tests for steps routes."""

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from services.content_service import get_all_phases

# Mark all tests in this module as integration tests (database required)
pytestmark = pytest.mark.integration


def _get_valid_topic():
    """Get a valid topic from content for testing."""
    phases = get_all_phases()
    if phases and phases[0].topics:
        topic = phases[0].topics[0]
        if topic.learning_steps:
            return topic
    return None


class TestCompleteStepEndpoint:
    """Tests for POST /api/steps/complete endpoint."""

    async def test_complete_first_step(self, authenticated_client: AsyncClient):
        """Test completing the first step of a topic."""
        topic = _get_valid_topic()
        if not topic:
            pytest.skip("No valid topic with steps in content")

        response = await authenticated_client.post(
            "/api/steps/complete",
            json={"topic_id": topic.id, "step_order": 1},
        )

        assert response.status_code == 201
        data = response.json()
        assert data["topic_id"] == topic.id
        assert data["step_order"] == 1
        assert "completed_at" in data

    async def test_returns_400_for_already_completed_step(
        self, authenticated_client: AsyncClient, db_session: AsyncSession
    ):
        """Test returns 400 when step already completed."""
        topic = _get_valid_topic()
        if not topic:
            pytest.skip("No valid topic with steps in content")

        # Complete step once
        await authenticated_client.post(
            "/api/steps/complete",
            json={"topic_id": topic.id, "step_order": 1},
        )

        # Try to complete again
        response = await authenticated_client.post(
            "/api/steps/complete",
            json={"topic_id": topic.id, "step_order": 1},
        )

        assert response.status_code == 400
        assert "already completed" in response.json()["detail"].lower()

    async def test_returns_400_for_out_of_order_step(
        self, authenticated_client: AsyncClient
    ):
        """Test returns 400 when trying to complete step out of order."""
        topic = _get_valid_topic()
        if not topic or len(topic.learning_steps) < 3:
            pytest.skip("Topic needs at least 3 steps")

        # Try to complete step 3 without completing 1 and 2
        response = await authenticated_client.post(
            "/api/steps/complete",
            json={"topic_id": topic.id, "step_order": 3},
        )

        assert response.status_code == 400
        assert "previous steps" in response.json()["detail"].lower()

    async def test_returns_404_for_unknown_topic(
        self, authenticated_client: AsyncClient
    ):
        """Test returns 404 for unknown topic ID (valid format, doesn't exist)."""
        # Use a valid format topic_id that doesn't exist in content
        response = await authenticated_client.post(
            "/api/steps/complete",
            json={"topic_id": "phase999-topic999", "step_order": 1},
        )

        assert response.status_code == 404

    async def test_returns_400_for_invalid_step_order(
        self, authenticated_client: AsyncClient
    ):
        """Test returns 400 for invalid step order."""
        topic = _get_valid_topic()
        if not topic:
            pytest.skip("No valid topic in content")

        response = await authenticated_client.post(
            "/api/steps/complete",
            json={"topic_id": topic.id, "step_order": 999},
        )

        assert response.status_code == 400

    async def test_returns_401_for_unauthenticated(
        self, unauthenticated_client: AsyncClient
    ):
        """Test returns 401 for unauthenticated request."""
        response = await unauthenticated_client.post(
            "/api/steps/complete",
            json={"topic_id": "phase0-topic1", "step_order": 1},
        )

        assert response.status_code == 401


class TestGetTopicStepProgress:
    """Tests for GET /api/steps/{topic_id} endpoint."""

    async def test_returns_progress_for_valid_topic(
        self, authenticated_client: AsyncClient
    ):
        """Test returns progress for a valid topic."""
        topic = _get_valid_topic()
        if not topic:
            pytest.skip("No valid topic in content")

        response = await authenticated_client.get(f"/api/steps/{topic.id}")

        assert response.status_code == 200
        data = response.json()
        assert data["topic_id"] == topic.id
        assert "completed_steps" in data
        assert "total_steps" in data
        assert "next_unlocked_step" in data

    async def test_returns_404_for_unknown_topic(
        self, authenticated_client: AsyncClient
    ):
        """Test returns 404 for unknown topic ID (valid format, doesn't exist)."""
        # Valid format but doesn't exist - returns 404
        response = await authenticated_client.get("/api/steps/phase999-topic999")

        assert response.status_code == 404

    async def test_returns_401_for_unauthenticated(
        self, unauthenticated_client: AsyncClient
    ):
        """Test returns 401 for unauthenticated request."""
        response = await unauthenticated_client.get("/api/steps/phase0-topic1")

        assert response.status_code == 401


class TestUncompleteStepEndpoint:
    """Tests for DELETE /api/steps/{topic_id}/{step_order} endpoint."""

    async def test_uncompletes_step(self, authenticated_client: AsyncClient):
        """Test uncompleting a completed step."""
        topic = _get_valid_topic()
        if not topic:
            pytest.skip("No valid topic in content")

        # First complete the step
        await authenticated_client.post(
            "/api/steps/complete",
            json={"topic_id": topic.id, "step_order": 1},
        )

        # Then uncomplete it
        response = await authenticated_client.delete(f"/api/steps/{topic.id}/1")

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"
        assert data["deleted_count"] >= 1

    async def test_returns_zero_for_not_completed_step(
        self, authenticated_client: AsyncClient
    ):
        """Test returns 0 deleted when step wasn't completed."""
        topic = _get_valid_topic()
        if not topic:
            pytest.skip("No valid topic in content")

        response = await authenticated_client.delete(f"/api/steps/{topic.id}/1")

        assert response.status_code == 200
        data = response.json()
        assert data["deleted_count"] == 0

    async def test_returns_404_for_unknown_topic(
        self, authenticated_client: AsyncClient
    ):
        """Test returns 404 for unknown topic ID (valid format, doesn't exist)."""
        # Valid format but doesn't exist - returns 404
        response = await authenticated_client.delete("/api/steps/phase999-topic999/1")

        assert response.status_code == 404

    async def test_returns_400_for_invalid_step_order(
        self, authenticated_client: AsyncClient
    ):
        """Test returns 400 for invalid step order."""
        topic = _get_valid_topic()
        if not topic:
            pytest.skip("No valid topic in content")

        response = await authenticated_client.delete(f"/api/steps/{topic.id}/999")

        assert response.status_code == 400

    async def test_returns_401_for_unauthenticated(
        self, unauthenticated_client: AsyncClient
    ):
        """Test returns 401 for unauthenticated request."""
        response = await unauthenticated_client.delete("/api/steps/phase0-topic1/1")

        assert response.status_code == 401
