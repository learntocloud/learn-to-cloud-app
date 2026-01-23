"""Tests for dashboard routes."""

import pytest
from httpx import AsyncClient

# Mark all tests in this module as integration tests (database required)
pytestmark = pytest.mark.integration


class TestGetDashboard:
    """Tests for GET /api/user/dashboard endpoint."""

    async def test_returns_dashboard_for_authenticated_user(
        self, authenticated_client: AsyncClient
    ):
        """Test returns dashboard data for authenticated user."""
        response = await authenticated_client.get("/api/user/dashboard")

        assert response.status_code == 200
        data = response.json()
        assert "user" in data
        assert "phases" in data
        assert "overall_progress" in data
        assert "badges" in data

    async def test_dashboard_user_data(self, authenticated_client: AsyncClient):
        """Test dashboard includes user data."""
        response = await authenticated_client.get("/api/user/dashboard")

        assert response.status_code == 200
        data = response.json()
        assert "user" in data
        assert "id" in data["user"]
        assert "email" in data["user"]

    async def test_returns_401_for_unauthenticated(
        self, unauthenticated_client: AsyncClient
    ):
        """Test returns 401 for unauthenticated request."""
        response = await unauthenticated_client.get("/api/user/dashboard")

        assert response.status_code == 401


class TestGetPhases:
    """Tests for GET /api/user/phases endpoint."""

    async def test_returns_phases_for_authenticated_user(
        self, authenticated_client: AsyncClient
    ):
        """Test returns phases for authenticated user."""
        response = await authenticated_client.get("/api/user/phases")

        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        if data:
            phase = data[0]
            assert "id" in phase
            assert "name" in phase
            assert "slug" in phase
            assert "is_locked" in phase

    async def test_returns_phases_for_unauthenticated_user(
        self, unauthenticated_client: AsyncClient
    ):
        """Test returns phases for unauthenticated user (limited access)."""
        response = await unauthenticated_client.get("/api/user/phases")

        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        # Phase 0 should be unlocked, others locked
        for phase in data:
            if phase["id"] == 0:
                assert phase["is_locked"] is False
            else:
                assert phase["is_locked"] is True

    async def test_phases_have_progress_for_authenticated(
        self, authenticated_client: AsyncClient
    ):
        """Test phases include progress for authenticated users."""
        response = await authenticated_client.get("/api/user/phases")

        assert response.status_code == 200
        data = response.json()
        # Progress may be null for phases with no activity
        # but the field should exist
        if data:
            # At least one phase should have progress key
            assert any("progress" in phase for phase in data)


class TestGetPhaseDetail:
    """Tests for GET /api/user/phases/{phase_slug} endpoint."""

    async def test_returns_phase_detail_for_authenticated(
        self, authenticated_client: AsyncClient
    ):
        """Test returns phase detail for authenticated user."""
        from services.content_service import get_all_phases

        phases = get_all_phases()
        if not phases:
            pytest.skip("No phases in content")

        phase_slug = phases[0].slug

        response = await authenticated_client.get(f"/api/user/phases/{phase_slug}")

        assert response.status_code == 200
        data = response.json()
        assert data["slug"] == phase_slug
        assert "topics" in data
        assert "hands_on_requirements" in data

    async def test_returns_phase_detail_for_unauthenticated(
        self, unauthenticated_client: AsyncClient
    ):
        """Test returns phase detail for unauthenticated user."""
        from services.content_service import get_all_phases

        phases = get_all_phases()
        if not phases:
            pytest.skip("No phases in content")

        phase_slug = phases[0].slug

        response = await unauthenticated_client.get(f"/api/user/phases/{phase_slug}")

        assert response.status_code == 200
        data = response.json()
        assert data["slug"] == phase_slug

    async def test_returns_404_for_nonexistent_phase(
        self, authenticated_client: AsyncClient
    ):
        """Test returns 404 for non-existent phase."""
        response = await authenticated_client.get("/api/user/phases/nonexistent-phase")

        assert response.status_code == 404

    async def test_topics_have_locking_status(self, authenticated_client: AsyncClient):
        """Test topics include locking status."""
        from services.content_service import get_all_phases

        phases = get_all_phases()
        if not phases:
            pytest.skip("No phases in content")

        phase_slug = phases[0].slug

        response = await authenticated_client.get(f"/api/user/phases/{phase_slug}")

        assert response.status_code == 200
        data = response.json()
        if data["topics"]:
            topic = data["topics"][0]
            assert "is_locked" in topic


class TestGetTopicDetail:
    """Tests for GET /api/user/phases/{phase_slug}/topics/{topic_slug} endpoint."""

    async def test_returns_topic_detail_for_authenticated(
        self, authenticated_client: AsyncClient
    ):
        """Test returns topic detail for authenticated user."""
        from services.content_service import get_all_phases

        phases = get_all_phases()
        if not phases or not phases[0].topics:
            pytest.skip("No topics in content")

        phase = phases[0]
        topic = phase.topics[0]

        response = await authenticated_client.get(
            f"/api/user/phases/{phase.slug}/topics/{topic.slug}"
        )

        assert response.status_code == 200
        data = response.json()
        assert data["slug"] == topic.slug
        assert "learning_steps" in data
        assert "questions" in data

    async def test_returns_topic_detail_for_unauthenticated(
        self, unauthenticated_client: AsyncClient
    ):
        """Test returns topic detail for unauthenticated user."""
        from services.content_service import get_all_phases

        phases = get_all_phases()
        if not phases or not phases[0].topics:
            pytest.skip("No topics in content")

        phase = phases[0]
        topic = phase.topics[0]

        response = await unauthenticated_client.get(
            f"/api/user/phases/{phase.slug}/topics/{topic.slug}"
        )

        assert response.status_code == 200
        data = response.json()
        assert data["slug"] == topic.slug

    async def test_returns_404_for_nonexistent_phase(
        self, authenticated_client: AsyncClient
    ):
        """Test returns 404 for non-existent phase."""
        response = await authenticated_client.get(
            "/api/user/phases/nonexistent-phase/topics/topic1"
        )

        assert response.status_code == 404

    async def test_returns_404_for_nonexistent_topic(
        self, authenticated_client: AsyncClient
    ):
        """Test returns 404 for non-existent topic."""
        from services.content_service import get_all_phases

        phases = get_all_phases()
        if not phases:
            pytest.skip("No phases in content")

        phase_slug = phases[0].slug

        response = await authenticated_client.get(
            f"/api/user/phases/{phase_slug}/topics/nonexistent-topic"
        )

        assert response.status_code == 404

    async def test_includes_progress_for_authenticated(
        self, authenticated_client: AsyncClient
    ):
        """Test includes progress data for authenticated users."""
        from services.content_service import get_all_phases

        phases = get_all_phases()
        if not phases or not phases[0].topics:
            pytest.skip("No topics in content")

        phase = phases[0]
        topic = phase.topics[0]

        response = await authenticated_client.get(
            f"/api/user/phases/{phase.slug}/topics/{topic.slug}"
        )

        assert response.status_code == 200
        data = response.json()
        assert "progress" in data
        assert "completed_step_orders" in data
        assert "passed_question_ids" in data
