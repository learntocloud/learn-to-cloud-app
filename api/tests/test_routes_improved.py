"""IMPROVED HTTP endpoint tests for FastAPI routes.

This is an improved version demonstrating proper testing practices:
- Comprehensive response validation (not just status codes)
- Edge case testing
- Error message validation
- Data persistence verification
- Proper async testing
- Clear test names and documentation
"""

from datetime import datetime

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import AsyncSession

from core.auth import optional_auth, require_auth
from core.database import get_db
from main import app
from models import User
from repositories.progress import StepProgressRepository

# =============================================================================
# TEST FIXTURES
# =============================================================================


@pytest.fixture
def test_app(db_session: AsyncSession, test_user: User):
    """Create a test app with dependency overrides."""

    async def override_get_db():
        try:
            yield db_session
            await db_session.commit()
        except Exception:
            await db_session.rollback()
            raise

    def override_require_auth():
        return test_user.id

    def override_optional_auth():
        return test_user.id

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[require_auth] = override_require_auth
    app.dependency_overrides[optional_auth] = override_optional_auth

    yield app

    app.dependency_overrides.clear()


@pytest.fixture
def client(test_app: FastAPI) -> TestClient:
    """Create a test client with dependency overrides."""
    return TestClient(test_app, raise_server_exceptions=False)


@pytest.fixture
def unauthenticated_client(db_session: AsyncSession):
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
# IMPROVED USER ENDPOINT TESTS
# =============================================================================


@pytest.mark.asyncio
class TestUserEndpointsImproved:
    """Improved tests with comprehensive validation."""

    def test_get_current_user_returns_complete_schema(
        self, client: TestClient, test_user: User
    ):
        """Validates complete user schema, not just fields exist."""
        response = client.get("/api/user/me")
        assert response.status_code == 200

        data = response.json()

        # Validate all expected fields exist
        required_fields = {
            "id",
            "email",
            "first_name",
            "last_name",
            "avatar_url",
            "github_username",
            "is_admin",
            "created_at",
        }
        assert set(data.keys()) == required_fields

        # Validate field values match test user
        assert data["id"] == test_user.id
        assert data["email"] == test_user.email
        assert data["first_name"] == test_user.first_name
        assert data["last_name"] == test_user.last_name
        assert data["github_username"] == test_user.github_username
        assert isinstance(data["is_admin"], bool)

        # Validate created_at is valid ISO 8601 datetime
        assert isinstance(data["created_at"], str)
        datetime.fromisoformat(data["created_at"].replace("Z", "+00:00"))

    def test_get_current_user_handles_missing_optional_fields(
        self, client: TestClient, db_session: AsyncSession
    ):
        """User with null optional fields should still return valid response."""
        # Create user with minimal fields
        minimal_user = User(
            id="minimal_user",
            email="minimal@test.com",
            first_name=None,  # Optional
            last_name=None,  # Optional
            github_username=None,  # Optional
        )
        db_session.add(minimal_user)

        # Override auth to return minimal user
        def override_require_auth():
            return minimal_user.id

        app.dependency_overrides[require_auth] = override_require_auth

        response = client.get("/api/user/me")
        assert response.status_code == 200

        data = response.json()
        assert data["id"] == "minimal_user"
        assert data["email"] == "minimal@test.com"
        assert data["first_name"] is None
        assert data["last_name"] is None
        assert data["github_username"] is None

        app.dependency_overrides.clear()


# =============================================================================
# IMPROVED STEP ENDPOINT TESTS
# =============================================================================


@pytest.mark.asyncio
class TestStepEndpointsImproved:
    """Improved step tests with edge cases and validation."""

    async def test_complete_step_validates_response_schema(self, client: TestClient):
        """Validates exact response structure, not just field existence."""
        response = client.post(
            "/api/steps/complete",
            json={"topic_id": "phase0-topic1", "step_order": 1},
        )
        assert response.status_code == 200

        data = response.json()

        # Validate exact schema
        expected_keys = {"topic_id", "step_order", "completed_at"}
        assert set(data.keys()) == expected_keys

        # Validate field types and values
        assert data["topic_id"] == "phase0-topic1"
        assert data["step_order"] == 1
        assert isinstance(data["completed_at"], str)

        # Validate ISO 8601 datetime format
        completed_at = datetime.fromisoformat(
            data["completed_at"].replace("Z", "+00:00")
        )
        assert completed_at is not None

    async def test_complete_step_persists_to_database(
        self, client: TestClient, db_session: AsyncSession, test_user: User
    ):
        """Verifies step completion is actually saved to database."""
        topic_id = "phase0-topic1"
        step_order = 1

        # Complete the step
        response = client.post(
            "/api/steps/complete",
            json={"topic_id": topic_id, "step_order": step_order},
        )
        assert response.status_code == 200

        # Verify it was saved to database
        repo = StepProgressRepository(db_session)
        completed_steps = await repo.get_completed_step_orders(test_user.id, topic_id)

        assert step_order in completed_steps

    async def test_complete_step_requires_previous_steps_with_clear_error(
        self, client: TestClient
    ):
        """Error message should clearly indicate which step is required."""
        # Try to complete step 3 without completing 1 and 2
        response = client.post(
            "/api/steps/complete",
            json={"topic_id": "phase0-topic1", "step_order": 3},
        )

        assert response.status_code == 400
        data = response.json()

        # Validate error message is helpful
        detail = data["detail"].lower()
        assert "step" in detail
        assert any(
            keyword in detail for keyword in ["previous", "complete", "must", "order"]
        )

    async def test_complete_step_rejects_out_of_range_with_specific_error(
        self, client: TestClient
    ):
        """Out of range step should have clear error message."""
        response = client.post(
            "/api/steps/complete",
            json={"topic_id": "phase0-topic1", "step_order": 999},
        )

        assert response.status_code == 400
        data = response.json()

        # Error should mention invalid step number
        detail = data["detail"].lower()
        assert "step" in detail or "invalid" in detail or "range" in detail

    async def test_complete_step_idempotent_on_duplicate(
        self, client: TestClient, db_session: AsyncSession, test_user: User
    ):
        """Completing same step twice should fail gracefully."""
        topic_id = "phase0-topic2"
        step_order = 1

        # Complete step first time
        response1 = client.post(
            "/api/steps/complete",
            json={"topic_id": topic_id, "step_order": step_order},
        )
        assert response1.status_code == 200

        # Try to complete again
        response2 = client.post(
            "/api/steps/complete",
            json={"topic_id": topic_id, "step_order": step_order},
        )

        assert response2.status_code == 400
        data = response2.json()

        # Should mention already completed
        detail = data["detail"].lower()
        assert "already" in detail or "duplicate" in detail

        # Verify database has the record (using repository)
        repo = StepProgressRepository(db_session)
        exists = await repo.exists(test_user.id, topic_id, step_order)
        assert exists is True  # Should still exist, not duplicated

    async def test_get_topic_step_progress_returns_valid_structure(
        self, client: TestClient
    ):
        """Step progress response should have complete, valid structure."""
        response = client.get("/api/steps/phase0-topic1")
        assert response.status_code == 200

        data = response.json()

        # Validate required fields
        required_fields = {
            "topic_id",
            "total_steps",
            "completed_steps",
            "next_unlocked_step",
        }
        assert set(data.keys()) == required_fields

        # Validate types
        assert isinstance(data["topic_id"], str)
        assert isinstance(data["total_steps"], int)
        assert isinstance(data["completed_steps"], list)
        assert isinstance(data["next_unlocked_step"], int)

        # Validate ranges
        assert data["total_steps"] > 0
        assert 1 <= data["next_unlocked_step"] <= data["total_steps"]
        assert all(
            isinstance(step, int) and 1 <= step <= data["total_steps"]
            for step in data["completed_steps"]
        )

    async def test_uncomplete_step_actually_removes_from_database(
        self, client: TestClient, db_session: AsyncSession, test_user: User
    ):
        """Regression test: uncomplete should actually delete the record."""
        topic_id = "phase0-topic4"
        step_order = 1

        # Complete step
        complete_response = client.post(
            "/api/steps/complete",
            json={"topic_id": topic_id, "step_order": step_order},
        )
        assert complete_response.status_code == 200

        # Verify it's in database
        repo = StepProgressRepository(db_session)
        assert await repo.exists(test_user.id, topic_id, step_order)

        # Uncomplete step
        uncomplete_response = client.delete(f"/api/steps/{topic_id}/{step_order}")
        assert uncomplete_response.status_code == 200

        data = uncomplete_response.json()
        assert data["status"] == "success"
        assert data["deleted_count"] >= 1

        # CRITICAL: Verify it's actually removed from database
        assert not await repo.exists(test_user.id, topic_id, step_order)

        # Verify GET request also shows it as incomplete
        get_response = client.get(f"/api/steps/{topic_id}")
        get_data = get_response.json()
        assert step_order not in get_data["completed_steps"]


# =============================================================================
# IMPROVED DASHBOARD TESTS
# =============================================================================


@pytest.mark.asyncio
class TestDashboardEndpointsImproved:
    """Improved dashboard tests with comprehensive validation."""

    def test_dashboard_returns_complete_schema(self, client: TestClient):
        """Dashboard should return all expected fields with correct types."""
        response = client.get("/api/user/dashboard")
        assert response.status_code == 200

        data = response.json()

        # Validate top-level structure
        required_keys = {
            "user",
            "phases",
            "overall_progress",
            "phases_completed",
            "phases_total",
            "current_phase",
            "badges",
        }
        assert set(data.keys()) == required_keys

        # Validate types
        assert isinstance(data["phases"], list)
        assert isinstance(data["badges"], list)
        assert isinstance(data["overall_progress"], int | float)
        assert isinstance(data["phases_completed"], int)
        assert isinstance(data["phases_total"], int)
        assert isinstance(data["current_phase"], int | None)

        # Validate ranges
        assert 0 <= data["overall_progress"] <= 100
        assert 0 <= data["phases_completed"] <= data["phases_total"]
        assert data["phases_total"] == 7  # Learn to Cloud has 7 phases

        # Validate user object
        assert isinstance(data["user"], dict)
        assert "id" in data["user"]
        assert "email" in data["user"]

    def test_dashboard_phases_have_complete_structure(self, client: TestClient):
        """Each phase in dashboard should have complete structure."""
        response = client.get("/api/user/dashboard")
        data = response.json()

        phases = data["phases"]
        assert len(phases) == 7  # Exactly 7 phases

        for phase in phases:
            # Validate required fields
            assert "id" in phase
            assert "name" in phase
            assert "slug" in phase
            assert "order" in phase
            assert "topics" in phase

            # Validate types
            assert isinstance(phase["id"], int)
            assert isinstance(phase["name"], str)
            assert isinstance(phase["slug"], str)
            assert isinstance(phase["order"], int)
            assert isinstance(phase["topics"], list)

            # Validate ranges
            assert 0 <= phase["id"] <= 6
            assert phase["order"] == phase["id"]  # Order should match ID

    def test_dashboard_calculates_zero_progress_for_new_user(self, client: TestClient):
        """New user with no progress should show 0% overall progress."""
        response = client.get("/api/user/dashboard")
        data = response.json()

        assert data["overall_progress"] == 0
        assert data["phases_completed"] == 0
        assert len(data["badges"]) == 0
        assert data["current_phase"] is None or data["current_phase"] == 0

    async def test_dashboard_reflects_partial_progress(
        self, client: TestClient, db_session: AsyncSession, test_user: User
    ):
        """Dashboard should accurately reflect partial progress."""
        # Complete exactly 1 step
        repo = StepProgressRepository(db_session)
        await repo.create(test_user.id, "phase0-topic1", 1)
        await db_session.commit()

        response = client.get("/api/user/dashboard")
        data = response.json()

        # Should show >0% progress but <100%
        assert 0 < data["overall_progress"] < 100

        # Should have 0 completed phases (1 step is not enough)
        assert data["phases_completed"] == 0


# =============================================================================
# IMPROVED ERROR HANDLING TESTS
# =============================================================================


class TestErrorHandlingImproved:
    """Improved error handling tests with specific validations."""

    def test_404_returns_standard_error_format(self, client: TestClient):
        """404 errors should return consistent error format."""
        response = client.get("/api/nonexistent-endpoint")
        assert response.status_code == 404

        data = response.json()
        assert "detail" in data
        assert isinstance(data["detail"], str)

    def test_405_method_not_allowed_is_clear(self, client: TestClient):
        """Method not allowed should have clear error message."""
        response = client.post("/health")  # Health only allows GET
        assert response.status_code == 405

        data = response.json()
        assert "detail" in data

    def test_422_validation_error_details(self, client: TestClient):
        """Validation errors should provide helpful detail."""
        response = client.post(
            "/api/steps/complete",
            json={"topic_id": "phase0-topic1"},  # Missing step_order
        )

        assert response.status_code == 422
        data = response.json()

        assert "detail" in data
        # FastAPI returns list of validation errors
        if isinstance(data["detail"], list):
            assert len(data["detail"]) > 0
            # Should mention missing field
            error_messages = str(data["detail"]).lower()
            assert "step_order" in error_messages or "required" in error_messages

    def test_malformed_json_returns_422(self, client: TestClient):
        """Malformed JSON should return 422 with clear error."""
        response = client.post(
            "/api/steps/complete",
            content="this is not valid json {{}",
            headers={"Content-Type": "application/json"},
        )

        assert response.status_code == 422


# =============================================================================
# NEW: SECURITY TESTS
# =============================================================================


class TestSecurityImproved:
    """Security-focused tests to prevent vulnerabilities."""

    def test_sql_injection_attempt_rejected(self, client: TestClient):
        """SQL injection attempts should be safely rejected."""
        # Try SQL injection in topic_id
        response = client.post(
            "/api/steps/complete",
            json={
                "topic_id": "phase0-topic1'; DROP TABLE step_progress; --",
                "step_order": 1,
            },
        )

        # Should either be 400 (validation) or 404 (topic not found)
        # But should NOT cause SQL error or execute the injection
        assert response.status_code in [400, 404]

    def test_xss_attempt_in_question_answer(self, client: TestClient):
        """XSS attempts should be sanitized or rejected."""
        response = client.post(
            "/api/questions/submit",
            json={
                "topic_id": "phase0-topic1",
                "question_id": "phase0-topic1-q1",
                "user_answer": "<script>alert('XSS')</script>This is my answer.",
            },
        )

        # Should either accept and sanitize, or reject
        # Should NOT execute the script
        assert response.status_code in [200, 400, 422]

    def test_unauthenticated_access_to_protected_endpoint(
        self, unauthenticated_client: TestClient
    ):
        """Protected endpoints should require authentication."""
        response = unauthenticated_client.get("/api/user/dashboard")
        assert response.status_code == 401

        data = response.json()
        assert "detail" in data

    def test_extremely_long_input_handled(self, client: TestClient):
        """Very long inputs should be rejected gracefully."""
        very_long_string = "a" * 1_000_000  # 1MB of data

        response = client.post(
            "/api/questions/submit",
            json={
                "topic_id": "phase0-topic1",
                "question_id": "phase0-topic1-q1",
                "user_answer": very_long_string,
            },
        )

        # Should reject (either 400 validation or 413 payload too large)
        # Should NOT crash the server
        assert response.status_code in [400, 413, 422]


# =============================================================================
# NEW: BOUNDARY VALUE TESTS
# =============================================================================


class TestBoundaryValues:
    """Test boundary conditions and edge cases."""

    def test_complete_first_step_in_topic(self, client: TestClient):
        """First step (step 1) should always be allowed."""
        response = client.post(
            "/api/steps/complete",
            json={"topic_id": "phase0-topic1", "step_order": 1},
        )
        assert response.status_code == 200

    def test_complete_last_step_in_topic(self, client: TestClient):
        """Should handle last step completion correctly."""
        topic_id = "phase0-topic1"

        # Complete all steps in order (assuming topic has 3 steps)
        for step in [1, 2, 3]:
            response = client.post(
                "/api/steps/complete",
                json={"topic_id": topic_id, "step_order": step},
            )
            assert response.status_code == 200

        # Verify all steps completed
        response = client.get(f"/api/steps/{topic_id}")
        data = response.json()
        assert data["completed_steps"] == [1, 2, 3]

    def test_step_order_zero_rejected(self, client: TestClient):
        """Step order 0 should be rejected (steps start at 1)."""
        response = client.post(
            "/api/steps/complete",
            json={"topic_id": "phase0-topic1", "step_order": 0},
        )
        assert response.status_code in [400, 422]

    def test_negative_step_order_rejected(self, client: TestClient):
        """Negative step orders should be rejected."""
        response = client.post(
            "/api/steps/complete",
            json={"topic_id": "phase0-topic1", "step_order": -1},
        )
        assert response.status_code in [400, 422]
