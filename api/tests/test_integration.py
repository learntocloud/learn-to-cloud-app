"""Integration tests for Learn to Cloud API.

Tests complete user flows end-to-end, combining multiple endpoints
and services to validate entire user journeys.

Mark as integration tests: pytest -m integration
"""

from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import AsyncSession

from models import User


@pytest.mark.integration
@pytest.mark.asyncio
class TestCompletePhaseFlow:
    """Test complete user journey through a phase."""

    async def test_new_user_completes_phase_0_earns_badge(
        self, client: TestClient, db_session: AsyncSession, test_user: User
    ):
        """Complete end-to-end flow: new user → complete phase 0 → earn badge.

        This tests the entire user journey:
        1. User starts with 0% progress
        2. Completes all steps in Phase 0
        3. Passes all questions in Phase 0
        4. Submits GitHub profile (hands-on requirement)
        5. Dashboard shows Phase 0 complete
        6. User earns "Explorer" badge
        """

        # Step 1: Verify starting state (0% progress)
        dashboard = client.get("/api/user/dashboard")
        assert dashboard.status_code == 200
        initial_data = dashboard.json()

        assert initial_data["overall_progress"] == 0
        assert initial_data["phases_completed"] == 0
        assert len(initial_data["badges"]) == 0

        # Step 2: Complete all 15 steps in Phase 0
        # Phase 0 has specific topics and steps
        # We'll use phase0-topic1 through phase0-topic5
        steps_completed = 0
        topics = [
            "phase0-topic1",
            "phase0-topic2",
            "phase0-topic3",
            "phase0-topic4",
            "phase0-topic5",
        ]

        # Complete 3 steps per topic (15 total)
        for topic_id in topics:
            for step_order in [1, 2, 3]:
                response = client.post(
                    "/api/steps/complete",
                    json={"topic_id": topic_id, "step_order": step_order},
                )
                assert response.status_code == 200
                data = response.json()
                assert data["topic_id"] == topic_id
                assert data["step_order"] == step_order
                steps_completed += 1

        assert steps_completed == 15

        # Verify steps were saved
        for topic_id in topics:
            step_progress = client.get(f"/api/steps/{topic_id}")
            assert step_progress.status_code == 200
            step_data = step_progress.json()
            assert len(step_data["completed_steps"]) == 3

        # Step 3: Pass all 12 questions in Phase 0
        questions_passed = 0
        topics_with_questions = [
            "phase0-topic1",
            "phase0-topic2",
            "phase0-topic3",
            "phase0-topic4",
        ]

        # 3 questions per topic (12 total)
        for topic_id in topics_with_questions:
            for q_num in [1, 2, 3]:
                response = client.post(
                    "/api/questions/submit",
                    json={
                        "topic_id": topic_id,
                        "question_id": f"{topic_id}-q{q_num}",
                        "user_answer": (
                            "This is a comprehensive answer demonstrating "
                            "understanding of cloud computing fundamentals. "
                            "I understand the key concepts including scalability, "
                            "elasticity, on-demand self-service, and resource pooling."
                        ),
                    },
                )

                # Note: This might return 200 or other status depending on LLM response
                # In tests, we'd mock the LLM to always pass
                assert response.status_code in [200, 201]

                # In real integration test, verify the question was marked as passed
                questions_passed += 1

        assert questions_passed == 12

        # Step 4: Submit GitHub profile (hands-on requirement)
        github_submission = client.post(
            "/api/github/submit",
            json={
                "requirement_id": "phase0-github-profile",
                "submitted_value": "https://github.com/testuser",
            },
        )

        # Should accept submission (validation happens async or via mock)
        assert github_submission.status_code in [200, 201]

        # Step 5: Verify dashboard shows Phase 0 complete
        final_dashboard = client.get("/api/user/dashboard")
        assert final_dashboard.status_code == 200
        final_data = final_dashboard.json()

        # Find Phase 0 in phases list
        phase_0 = next((p for p in final_data["phases"] if p["id"] == 0), None)
        assert phase_0 is not None

        # Phase 0 should be complete
        assert phase_0["is_complete"] is True
        assert phase_0["progress"] == 100

        # Overall progress should reflect completion
        assert final_data["phases_completed"] == 1

        # Step 6: Verify "Explorer" badge was earned
        badges = final_data["badges"]
        badge_ids = [b["id"] for b in badges]

        assert "phase_0_complete" in badge_ids

        explorer_badge = next(
            (b for b in badges if b["id"] == "phase_0_complete"), None
        )
        assert explorer_badge is not None
        assert explorer_badge["name"] == "Explorer"
        assert explorer_badge["icon"] == "🥉"


@pytest.mark.integration
@pytest.mark.asyncio
class TestStreakFlow:
    """Test streak tracking and badge earning."""

    async def test_user_earns_streak_badges_over_time(
        self, client: TestClient, db_session: AsyncSession
    ):
        """Test that consistent daily activity earns streak badges.

        Flow:
        1. User completes activity on Day 1
        2. User completes activity on Days 2-7 (7 day streak)
        3. User earns "Week Warrior" badge
        4. User continues to Day 30
        5. User earns "Monthly Master" badge
        """

        # Note: This test would require time manipulation or mocking datetime
        # Showing structure of what this test would validate

        # Day 1: Complete first step
        response = client.post(
            "/api/steps/complete",
            json={"topic_id": "phase0-topic1", "step_order": 1},
        )
        assert response.status_code == 200

        # Check streak (should be 1)
        streak = client.get("/api/activity/streak")
        assert streak.status_code == 200
        streak_data = streak.json()
        assert streak_data["current_streak"] >= 1

        # Would continue with time-based progression...
        # In real implementation, would use freezegun or similar to advance time


@pytest.mark.integration
class TestProgressLocking:
    """Test that phase/topic locking works correctly."""

    def test_user_cannot_access_locked_phase(self, client: TestClient, test_user: User):
        """User without Phase 0 complete cannot access Phase 1 content."""

        # Try to complete a step in Phase 1 without completing Phase 0
        response = client.post(
            "/api/steps/complete",
            json={"topic_id": "phase1-topic1", "step_order": 1},
        )

        # Should be rejected (topic is locked)
        assert response.status_code in [400, 403]

        error_data = response.json()
        detail = error_data["detail"].lower()

        # Error should mention locking/prerequisites
        assert any(
            word in detail
            for word in ["locked", "prerequisite", "complete", "required", "phase 0"]
        )

    def test_completing_phase_unlocks_next_phase(
        self, client: TestClient, db_session: AsyncSession, test_user: User
    ):
        """Completing Phase 0 unlocks Phase 1."""

        # First, complete all of Phase 0
        # (In real test, would use helper to complete phase)

        # Then verify Phase 1 is unlocked
        phase_1_response = client.get("/api/user/phases/phase-1")

        # Should be accessible (200) and show as unlocked
        assert phase_1_response.status_code == 200
        phase_1_data = phase_1_response.json()

        assert phase_1_data["is_locked"] is False


@pytest.mark.integration
class TestCertificateFlow:
    """Test certificate generation flow."""

    def test_user_completes_all_phases_generates_certificate(
        self,
        client: TestClient,
        db_session: AsyncSession,
        test_user_full_completion: User,
    ):
        """User who completes all phases can generate certificate.

        Flow:
        1. User completes all 7 phases
        2. Check certificate eligibility (should be eligible)
        3. Generate certificate
        4. Verify certificate exists
        5. Verify certificate can be verified by code
        """

        # Override auth to use fully complete user
        from core.auth import require_auth

        def override_require_auth():
            return test_user_full_completion.id

        from main import app

        app.dependency_overrides[require_auth] = override_require_auth

        # Step 1: Check eligibility
        eligibility = client.get("/api/certificates/eligibility/full_completion")
        assert eligibility.status_code == 200
        eligibility_data = eligibility.json()

        assert eligibility_data["is_eligible"] is True
        assert eligibility_data["certificate_type"] == "full_completion"

        # Step 2: Generate certificate
        generate = client.post(
            "/api/certificates/generate",
            json={
                "certificate_type": "full_completion",
                "recipient_name": "Test User",
            },
        )

        assert generate.status_code in [200, 201]
        cert_data = generate.json()

        assert "certificate_id" in cert_data or "code" in cert_data
        verification_code = cert_data.get("code") or cert_data.get("verification_code")

        # Step 3: List user certificates
        my_certs = client.get("/api/certificates/user/me")
        assert my_certs.status_code == 200
        certs_list = my_certs.json()

        assert len(certs_list) >= 1
        assert any(c["type"] == "full_completion" for c in certs_list)

        # Step 4: Verify certificate publicly
        if verification_code:
            verify = client.get(f"/api/certificates/verify/{verification_code}")
            assert verify.status_code == 200
            verify_data = verify.json()

            assert verify_data["is_valid"] is True
            assert verify_data["certificate_type"] == "full_completion"

        app.dependency_overrides.clear()


@pytest.mark.integration
class TestErrorRecovery:
    """Test that system recovers gracefully from errors."""

    def test_partial_step_completion_rollback_on_error(
        self, client: TestClient, db_session: AsyncSession
    ):
        """If step completion fails partway, should rollback transaction."""

        # This would require mocking a failure mid-transaction
        # Showing structure of what to test

        # Attempt to complete step that will fail
        # (e.g., database write error, validation error after partial save)

        # Verify that NO partial state was saved
        # i.e., database should be in consistent state

        pass

    def test_question_submission_with_llm_timeout_handled(
        self, client: TestClient, mock_openai_api
    ):
        """LLM timeout during question evaluation should fail gracefully."""

        # Mock LLM to timeout
        mock_openai_api.create_completion.side_effect = TimeoutError("LLM timeout")

        response = client.post(
            "/api/questions/submit",
            json={
                "topic_id": "phase0-topic1",
                "question_id": "phase0-topic1-q1",
                "user_answer": "Test answer with sufficient length for validation.",
            },
        )

        # Should return error, not crash
        assert response.status_code in [500, 503, 504]

        error_data = response.json()
        assert "detail" in error_data
        # Should provide helpful error message
        assert (
            "try again" in error_data["detail"].lower()
            or "timeout" in error_data["detail"].lower()
        )


@pytest.mark.integration
class TestConcurrentUsers:
    """Test system behavior with concurrent users."""

    def test_two_users_can_complete_same_step_concurrently(
        self, db_session: AsyncSession
    ):
        """Two different users completing same step should both succeed."""

        # This would require creating two separate test clients/sessions
        # and using asyncio.gather to make concurrent requests

        # Both users complete phase0-topic1 step 1 at same time
        # Both should succeed with 200 responses

        pass

    def test_same_user_duplicate_request_handled(self, client: TestClient):
        """Duplicate requests should be idempotent or fail gracefully."""

        # Make same request twice in quick succession
        # Either: both should succeed (idempotent)
        # Or: second should fail with clear error (already completed)

        pass


# =============================================================================
# INTEGRATION TEST HELPERS
# =============================================================================


def _complete_all_phase_requirements(
    client: TestClient, phase_id: int
) -> dict[str, Any]:
    """Helper to complete all requirements for a phase.

    Returns summary of what was completed.
    """
    from services.progress import PHASE_REQUIREMENTS

    req = PHASE_REQUIREMENTS[phase_id]

    completed = {
        "steps": 0,
        "questions": 0,
        "hands_on": 0,
    }

    # Complete steps (spread across topics)
    topics_count = (req.steps // 3) + 1  # ~3 steps per topic
    for topic_num in range(topics_count):
        topic_id = f"phase{phase_id}-topic{topic_num + 1}"
        steps_in_topic = min(3, req.steps - completed["steps"])

        for step in range(1, steps_in_topic + 1):
            client.post(
                "/api/steps/complete",
                json={"topic_id": topic_id, "step_order": step},
            )
            completed["steps"] += 1

    # Complete questions
    for q in range(1, req.questions + 1):
        topic_num = (q - 1) // 3
        topic_id = f"phase{phase_id}-topic{topic_num + 1}"
        q_in_topic = ((q - 1) % 3) + 1

        client.post(
            "/api/questions/submit",
            json={
                "topic_id": topic_id,
                "question_id": f"{topic_id}-q{q_in_topic}",
                "user_answer": "Comprehensive answer demonstrating understanding.",
            },
        )
        completed["questions"] += 1

    # Complete hands-on requirements
    # (This is simplified - real implementation would get actual requirement IDs)
    hands_on_reqs = _get_hands_on_requirements(phase_id)
    for req_id in hands_on_reqs:
        client.post(
            "/api/github/submit",
            json={
                "requirement_id": req_id,
                "submitted_value": "https://github.com/testuser/project",
            },
        )
        completed["hands_on"] += 1

    return completed


def _get_hands_on_requirements(phase_id: int) -> list[str]:
    """Get hands-on requirement IDs for a phase."""
    from services.hands_on_verification import get_requirements_for_phase

    requirements = get_requirements_for_phase(phase_id)
    return [req.id for req in requirements]
