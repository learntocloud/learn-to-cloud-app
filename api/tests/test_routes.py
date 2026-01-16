"""HTTP endpoint tests for FastAPI routes.

Tests the full request/response cycle using FastAPI's TestClient with
dependency overrides for authentication and database session.
"""

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import AsyncSession

from core.auth import optional_auth, require_auth
from core.database import get_db
from main import app
from models import User

# =============================================================================
# TEST FIXTURES
# =============================================================================


@pytest.fixture
def test_app(db_session: AsyncSession, test_user: User) -> FastAPI:
    """Create a test app with dependency overrides."""

    # Override database dependency - must commit like the real get_db does
    async def override_get_db():
        try:
            yield db_session
            await db_session.commit()
        except Exception:
            await db_session.rollback()
            raise

    # Override auth to return test user ID
    def override_require_auth():
        return test_user.id

    def override_optional_auth():
        return test_user.id

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[require_auth] = override_require_auth
    app.dependency_overrides[optional_auth] = override_optional_auth

    yield app

    # Clean up overrides
    app.dependency_overrides.clear()


@pytest.fixture
def client(test_app: FastAPI) -> TestClient:
    """Create a test client with dependency overrides."""
    return TestClient(test_app, raise_server_exceptions=False)


@pytest.fixture
def unauthenticated_client(db_session: AsyncSession) -> TestClient:
    """Create a test client without authentication."""

    async def override_get_db():
        try:
            yield db_session
            await db_session.commit()
        except Exception:
            await db_session.rollback()
            raise

    def override_require_auth():
        from fastapi import HTTPException

        raise HTTPException(status_code=401, detail="Unauthorized")

    def override_optional_auth():
        return None

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[require_auth] = override_require_auth
    app.dependency_overrides[optional_auth] = override_optional_auth

    yield TestClient(app, raise_server_exceptions=False)

    app.dependency_overrides.clear()


# =============================================================================
# HEALTH ENDPOINT TESTS
# =============================================================================


class TestHealthEndpoints:
    """Tests for /health endpoints."""

    def test_health_check(self, client: TestClient):
        """GET /health returns 200."""
        response = client.get("/health")
        assert response.status_code == 200
        data = response.json()
        assert "status" in data

    def test_ready_check(self, client: TestClient):
        """GET /ready returns status (may be 503 during startup)."""
        response = client.get("/ready")
        # May be 503 if init_done is not set in test environment
        assert response.status_code in [200, 503]


# =============================================================================
# USER ENDPOINT TESTS
# =============================================================================


class TestUserEndpoints:
    """Tests for /api/user endpoints."""

    def test_get_current_user(self, client: TestClient, test_user: User):
        """GET /api/user/me returns current user info."""
        response = client.get("/api/user/me")
        assert response.status_code == 200
        data = response.json()
        assert data["id"] == test_user.id
        assert data["email"] == test_user.email

    def test_get_current_user_unauthenticated(self, unauthenticated_client: TestClient):
        """GET /api/user/me returns 401 when not authenticated."""
        response = unauthenticated_client.get("/api/user/me")
        assert response.status_code == 401

    def test_get_public_profile_not_found(self, client: TestClient):
        """GET /api/user/profile/{username} returns 404 for non-existent user."""
        response = client.get("/api/user/profile/nonexistent_user_12345")
        assert response.status_code == 404


# =============================================================================
# STEP ENDPOINT TESTS
# =============================================================================


class TestStepEndpoints:
    """Tests for /api/steps endpoints."""

    def test_get_topic_step_progress(self, client: TestClient):
        """GET /api/steps/{topic_id} returns step progress."""
        response = client.get("/api/steps/phase0-topic0?total_steps=5")
        assert response.status_code == 200
        data = response.json()
        assert data["topic_id"] == "phase0-topic0"
        assert data["total_steps"] == 5
        assert "completed_steps" in data
        assert "next_unlocked_step" in data

    def test_complete_step(self, client: TestClient):
        """POST /api/steps/complete marks a step as complete."""
        response = client.post(
            "/api/steps/complete", json={"topic_id": "phase0-topic0", "step_order": 1}
        )
        assert response.status_code == 200
        data = response.json()
        assert data["topic_id"] == "phase0-topic0"
        assert data["step_order"] == 1
        assert "completed_at" in data

    def test_complete_step_sequential_required(self, client: TestClient):
        """POST /api/steps/complete fails when skipping steps."""
        # Try to complete step 3 without completing 1 and 2
        response = client.post(
            "/api/steps/complete", json={"topic_id": "phase0-topic1", "step_order": 3}
        )
        assert response.status_code == 400
        detail = response.json()["detail"].lower()
        assert "previous" in detail or "must complete" in detail

    def test_complete_step_duplicate(self, client: TestClient):
        """POST /api/steps/complete fails for already completed step."""
        # Complete step 1
        response = client.post(
            "/api/steps/complete", json={"topic_id": "phase0-topic2", "step_order": 1}
        )
        assert response.status_code == 200

        # Try to complete again
        response = client.post(
            "/api/steps/complete", json={"topic_id": "phase0-topic2", "step_order": 1}
        )
        assert response.status_code == 400
        assert "already" in response.json()["detail"].lower()

    def test_uncomplete_step(self, client: TestClient):
        """DELETE /api/steps/{topic_id}/{step_order} uncompletes a step."""
        # First complete a step
        client.post(
            "/api/steps/complete", json={"topic_id": "phase0-topic3", "step_order": 1}
        )

        # Then uncomplete it
        response = client.delete("/api/steps/phase0-topic3/1")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"

    def test_uncomplete_step_persists(self, client: TestClient):
        """Verify that uncomplete step actually removes the completion.

        Regression test: Ensure that after uncompleting a step,
        subsequent reads show the step as incomplete.
        """
        topic_id = "phase0-topic4"

        # Complete step 1
        response = client.post(
            "/api/steps/complete", json={"topic_id": topic_id, "step_order": 1}
        )
        assert response.status_code == 200

        # Verify step 1 is complete
        response = client.get(f"/api/steps/{topic_id}?total_steps=5")
        assert response.status_code == 200
        data = response.json()
        assert 1 in data["completed_steps"]

        # Uncomplete step 1
        response = client.delete(f"/api/steps/{topic_id}/1")
        assert response.status_code == 200
        assert response.json()["deleted_count"] >= 1

        # CRITICAL: Verify step 1 is NO LONGER in completed_steps
        response = client.get(f"/api/steps/{topic_id}?total_steps=5")
        assert response.status_code == 200
        data = response.json()
        assert (
            1 not in data["completed_steps"]
        ), f"Step 1 should be uncompleted but still in completed_steps: {data}"

    def test_get_all_steps_status(self, client: TestClient):
        """GET /api/steps/user/all-status returns all step progress."""
        response = client.get("/api/steps/user/all-status")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, dict)


# =============================================================================
# QUESTION ENDPOINT TESTS
# =============================================================================


class TestQuestionEndpoints:
    """Tests for /api/questions endpoints."""

    def test_get_topic_questions_status(self, client: TestClient):
        """GET /api/questions/topic/{topic_id}/status returns question status."""
        response = client.get("/api/questions/topic/phase0-topic0/status")
        assert response.status_code == 200
        data = response.json()
        assert data["topic_id"] == "phase0-topic0"
        assert "questions" in data
        assert "all_passed" in data

    def test_get_topic_questions_invalid_format(self, client: TestClient):
        """GET /api/questions/topic/{topic_id}/status validates topic_id format."""
        response = client.get("/api/questions/topic/invalid-format/status")
        assert response.status_code == 422  # Validation error

    def test_get_all_questions_status(self, client: TestClient):
        """GET /api/questions/user/all-status returns all question progress."""
        response = client.get("/api/questions/user/all-status")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, dict)

    def test_submit_question_invalid_format(self, client: TestClient):
        """POST /api/questions/submit validates question_id format."""
        response = client.post(
            "/api/questions/submit",
            json={
                "topic_id": "phase0-topic0",
                "question_id": "invalid",  # Missing proper format
                "user_answer": "Test answer",
            },
        )
        assert response.status_code == 400
        assert "format" in response.json()["detail"].lower()


# =============================================================================
# GITHUB/HANDS-ON ENDPOINT TESTS
# =============================================================================


class TestGitHubEndpoints:
    """Tests for /api/github endpoints."""

    def test_get_all_requirements(self, client: TestClient):
        """GET /api/github/requirements returns all phase requirements."""
        response = client.get("/api/github/requirements")
        assert response.status_code == 200
        data = response.json()
        assert "phases" in data
        assert len(data["phases"]) == 7  # 7 phases

    def test_get_phase_requirements(self, client: TestClient):
        """GET /api/github/requirements/{phase_id} returns phase requirements."""
        response = client.get("/api/github/requirements/0")
        assert response.status_code == 200
        data = response.json()
        assert data["phase_id"] == 0
        assert "requirements" in data
        assert "submissions" in data

    def test_get_user_submissions(self, client: TestClient):
        """GET /api/github/submissions returns user submissions."""
        response = client.get("/api/github/submissions")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)

    def test_submit_validation_requirement_not_found(self, client: TestClient):
        """POST /api/github/submit returns 404 for invalid requirement."""
        response = client.post(
            "/api/github/submit",
            json={
                "requirement_id": "nonexistent-requirement",
                "submitted_value": "https://github.com/test",
            },
        )
        assert response.status_code == 404


# =============================================================================
# DASHBOARD ENDPOINT TESTS
# =============================================================================


class TestDashboardEndpoints:
    """Tests for /api/user/dashboard endpoints."""

    def test_get_dashboard(self, client: TestClient):
        """GET /api/user/dashboard returns user dashboard data."""
        response = client.get("/api/user/dashboard")
        assert response.status_code == 200
        data = response.json()
        assert "phases" in data
        assert "badges" in data
        assert "overall_progress" in data
        assert "current_phase" in data


# =============================================================================
# ACTIVITY ENDPOINT TESTS
# =============================================================================


class TestActivityEndpoints:
    """Tests for /api/activity endpoints."""

    def test_get_streak(self, client: TestClient):
        """GET /api/activity/streak returns streak data."""
        response = client.get("/api/activity/streak")
        assert response.status_code == 200
        data = response.json()
        assert "current_streak" in data
        assert "longest_streak" in data

    def test_get_heatmap(self, client: TestClient):
        """GET /api/activity/heatmap returns activity heatmap."""
        response = client.get("/api/activity/heatmap")
        assert response.status_code == 200
        data = response.json()
        assert "days" in data


# =============================================================================
# CERTIFICATE ENDPOINT TESTS
# =============================================================================


class TestCertificateEndpoints:
    """Tests for /api/certificates endpoints."""

    def test_check_eligibility_not_complete(self, client: TestClient):
        """GET /api/certificates/eligibility: not eligible for incomplete user."""
        response = client.get("/api/certificates/eligibility/full_completion")
        assert response.status_code == 200
        data = response.json()
        assert data["is_eligible"] is False


@pytest.mark.asyncio
class TestCertificateEligibilityComplete:
    """Tests for certificate eligibility with complete user."""

    async def test_check_eligibility_complete(
        self, db_session: AsyncSession, test_user_full_completion: User
    ):
        """User with all phases complete is eligible for certificate."""
        from services.certificates import check_eligibility

        result = await check_eligibility(
            db_session, test_user_full_completion.id, "full_completion"
        )
        assert result.is_eligible is True


# =============================================================================
# ERROR HANDLING TESTS
# =============================================================================


class TestErrorHandling:
    """Tests for API error handling."""

    def test_404_for_unknown_route(self, client: TestClient):
        """Unknown routes return 404."""
        response = client.get("/api/nonexistent")
        assert response.status_code == 404

    def test_405_for_wrong_method(self, client: TestClient):
        """Wrong HTTP method returns 405."""
        response = client.post("/health")  # Health endpoint only allows GET
        assert response.status_code == 405

    def test_422_for_invalid_json(self, client: TestClient):
        """Invalid request body returns 422."""
        response = client.post(
            "/api/steps/complete",
            content="not valid json",
            headers={"Content-Type": "application/json"},
        )
        assert response.status_code == 422
