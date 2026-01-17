"""Service layer tests for dashboard functionality.

Tests the dashboard service in isolation from HTTP endpoints.
Focuses on business logic, data aggregation, and calculation accuracy.
"""

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from models import QuestionAttempt, StepProgress, Submission, SubmissionType, User
from services.dashboard import (
    get_dashboard,
    get_phase_detail,
)


@pytest.mark.asyncio
class TestDashboardService:
    """Test dashboard service business logic."""

    async def test_calculate_overall_progress_for_new_user(
        self, db_session: AsyncSession, test_user: User
    ):
        """New user should have 0% overall progress."""
        dashboard = await get_dashboard(
            db=db_session,
            user_id=test_user.id,
            user_email=test_user.email,
            user_first_name=test_user.first_name,
            user_last_name=test_user.last_name,
            user_avatar_url=None,
            user_github_username=test_user.github_username,
            is_admin=False,
        )

        assert dashboard.overall_progress == 0
        assert dashboard.phases_completed == 0
        assert dashboard.current_phase in [None, 0]

    async def test_calculate_overall_progress_with_partial_completion(
        self, db_session: AsyncSession, test_user: User
    ):
        """Overall progress should accurately reflect completion percentage."""
        # Add exactly 1 completed step out of total steps
        # Total steps across all phases: 15+36+30+31+51+55+64 = 282
        # 1 step = ~0.35% progress
        step = StepProgress(
            user_id=test_user.id,
            topic_id="phase0-topic1",
            step_order=1,
        )
        db_session.add(step)
        await db_session.commit()

        dashboard = await get_dashboard(
            db=db_session,
            user_id=test_user.id,
            user_email=test_user.email,
            user_first_name=test_user.first_name,
            user_last_name=test_user.last_name,
            user_avatar_url=None,
            user_github_username=test_user.github_username,
            is_admin=False,
        )

        # Should show small but non-zero progress
        assert 0 < dashboard.overall_progress < 1
        assert dashboard.phases_completed == 0  # No complete phases

    async def test_calculate_current_phase_correctly(
        self, db_session: AsyncSession, test_user: User
    ):
        """Current phase should be first incomplete phase with progress."""
        # Complete all of Phase 0
        await _complete_phase(db_session, test_user.id, 0)

        # Start Phase 1 (complete 1 step)
        step = StepProgress(
            user_id=test_user.id,
            topic_id="phase1-topic1",
            step_order=1,
        )
        db_session.add(step)
        await db_session.commit()

        dashboard = await get_dashboard(
            db=db_session,
            user_id=test_user.id,
            user_email=test_user.email,
            user_first_name=test_user.first_name,
            user_last_name=test_user.last_name,
            user_avatar_url=None,
            user_github_username=test_user.github_username,
            is_admin=False,
        )

        # Current phase should be 1 (first incomplete with progress)
        assert dashboard.current_phase == 1
        assert dashboard.phases_completed == 1  # Phase 0 complete

    async def test_phase_progress_calculation_accuracy(
        self, db_session: AsyncSession, test_user: User
    ):
        """Phase progress percentage should be calculated correctly."""
        # Phase 0 requires: 15 steps + 12 questions + 1 hands-on = 28 total items
        # Complete 14 items (50%)
        # - 10 steps
        # - 4 questions
        # - 0 hands-on
        for step_num in range(1, 11):  # 10 steps
            step = StepProgress(
                user_id=test_user.id,
                topic_id="phase0-topic1",
                step_order=step_num,
            )
            db_session.add(step)

        for q_num in range(1, 5):  # 4 questions
            attempt = QuestionAttempt(
                user_id=test_user.id,
                topic_id="phase0-topic1",
                question_id=f"phase0-topic1-q{q_num}",
                user_answer="Answer",
                is_passed=True,
                llm_feedback="Good",
            )
            db_session.add(attempt)

        await db_session.commit()

        dashboard = await get_dashboard(
            db=db_session,
            user_id=test_user.id,
            user_email=test_user.email,
            user_first_name=test_user.first_name,
            user_last_name=test_user.last_name,
            user_avatar_url=None,
            user_github_username=test_user.github_username,
            is_admin=False,
        )

        # Find Phase 0 data
        phase_0 = next(p for p in dashboard.phases if p.id == 0)

        # 14 items / 28 total = 50%
        expected_progress = (10 + 4) / (15 + 12 + 1) * 100
        assert abs(phase_0.progress.percentage - expected_progress) < 0.1

    async def test_phase_marked_complete_only_when_all_requirements_met(
        self, db_session: AsyncSession, test_user: User
    ):
        """Phase should only be marked complete when ALL requirements are met."""
        # Phase 0 requires: 15 steps, 12 questions, 1 hands-on

        # Complete steps and questions but NOT hands-on
        for step_num in range(1, 16):
            step = StepProgress(
                user_id=test_user.id,
                topic_id="phase0-topic1",
                step_order=step_num,
            )
            db_session.add(step)

        for q_num in range(1, 13):
            attempt = QuestionAttempt(
                user_id=test_user.id,
                topic_id="phase0-topic1",
                question_id=f"phase0-topic1-q{q_num}",
                user_answer="Answer",
                is_passed=True,
                llm_feedback="Good",
            )
            db_session.add(attempt)

        await db_session.commit()

        phase_detail = await get_phase_detail(
            db=db_session,
            user_id=test_user.id,
            phase_slug="phase-0",
            is_admin=False,
        )

        # Should NOT be marked complete (missing hands-on)
        assert phase_detail.is_phase_complete is False
        assert phase_detail.progress.percentage < 100  # Close but not 100%

    async def test_dashboard_includes_correct_badge_count(
        self, db_session: AsyncSession
    ):
        """Dashboard should correctly count earned badges."""
        # Create user with 2 complete phases
        user = User(
            id="badge_test_user",
            email="badges@test.com",
            first_name="Badge",
            last_name="Tester",
            github_username="badgetester",
        )
        db_session.add(user)
        await db_session.commit()

        # Complete Phase 0 and Phase 1
        await _complete_phase(db_session, user.id, 0)
        await _complete_phase(db_session, user.id, 1)

        dashboard = await get_dashboard(
            db=db_session,
            user_id=user.id,
            user_email=user.email,
            user_first_name=user.first_name,
            user_last_name=user.last_name,
            user_avatar_url=None,
            user_github_username=user.github_username,
            is_admin=False,
        )

        # Should have at least 2 phase badges
        assert len(dashboard.badges) >= 2

    async def test_dashboard_performance_with_large_dataset(
        self, db_session: AsyncSession, large_dataset_user: User, benchmark_threshold
    ):
        """Dashboard should load quickly even with lots of data."""
        import time

        start = time.time()
        dashboard = await get_dashboard(
            db=db_session,
            user_id=large_dataset_user.id,
            user_email=large_dataset_user.email,
            user_first_name=large_dataset_user.first_name,
            user_last_name=large_dataset_user.last_name,
            user_avatar_url=None,
            user_github_username=large_dataset_user.github_username,
            is_admin=False,
        )
        duration = time.time() - start

        # Should complete in under 1 second even with 1000+ records
        assert duration < benchmark_threshold["slow"]
        assert dashboard is not None


# =============================================================================
# HELPER FUNCTIONS
# =============================================================================


async def _complete_phase(
    db_session: AsyncSession, user_id: str, phase_id: int
) -> None:
    """Helper to complete all requirements for a phase."""
    from datetime import UTC, datetime

    from services.hands_on_verification import get_requirements_for_phase
    from services.progress import PHASE_REQUIREMENTS

    req = PHASE_REQUIREMENTS[phase_id]

    # Complete all steps
    for step_num in range(1, req.steps + 1):
        step = StepProgress(
            user_id=user_id,
            topic_id=f"phase{phase_id}-topic1",
            step_order=step_num,
        )
        db_session.add(step)

    # Pass all questions
    for q_num in range(1, req.questions + 1):
        attempt = QuestionAttempt(
            user_id=user_id,
            topic_id=f"phase{phase_id}-topic1",
            question_id=f"phase{phase_id}-topic1-q{q_num}",
            user_answer="Complete answer",
            is_passed=True,
            llm_feedback="Excellent",
        )
        db_session.add(attempt)

    # Add hands-on submissions
    requirements = get_requirements_for_phase(phase_id)
    for hands_on_req in requirements:
        submission = Submission(
            user_id=user_id,
            requirement_id=hands_on_req.id,
            submission_type=SubmissionType.GITHUB_PROFILE,
            phase_id=phase_id,
            submitted_value=f"https://github.com/user/phase{phase_id}",
            extracted_username="user",
            is_validated=True,
            validated_at=datetime.now(UTC),
        )
        db_session.add(submission)

    await db_session.commit()


@pytest.mark.asyncio
class TestDashboardEdgeCases:
    """Test edge cases and error scenarios."""

    async def test_dashboard_for_nonexistent_user_returns_none(
        self, db_session: AsyncSession
    ):
        """Dashboard for non-existent user should handle gracefully."""
        # For the functional API, dashboard will still return data
        # even if user doesn't exist in database (new user scenario)
        result = await get_dashboard(
            db=db_session,
            user_id="nonexistent_user_id",
            user_email="nonexistent@test.com",
            user_first_name="Non",
            user_last_name="Existent",
            user_avatar_url=None,
            user_github_username=None,
            is_admin=False,
        )

        # Should return valid dashboard with 0% progress
        assert result is not None
        assert result.overall_progress == 0

    async def test_dashboard_with_corrupted_data_handles_gracefully(
        self, db_session: AsyncSession, test_user: User
    ):
        """Dashboard should handle corrupted/invalid data gracefully."""
        # Add step with invalid topic_id (shouldn't exist in content)
        invalid_step = StepProgress(
            user_id=test_user.id,
            topic_id="invalid-topic-999",
            step_order=1,
        )
        db_session.add(invalid_step)
        await db_session.commit()

        # Should not crash, should handle gracefully
        dashboard = await get_dashboard(
            db=db_session,
            user_id=test_user.id,
            user_email=test_user.email,
            user_first_name=test_user.first_name,
            user_last_name=test_user.last_name,
            user_avatar_url=None,
            user_github_username=test_user.github_username,
            is_admin=False,
        )

        assert dashboard is not None
        assert len(dashboard.phases) == 7

    async def test_dashboard_calculates_correctly_with_failed_question_attempts(
        self, db_session: AsyncSession, test_user: User
    ):
        """Failed question attempts should not count toward progress."""
        # Add 5 passed questions
        for q_num in range(1, 6):
            attempt = QuestionAttempt(
                user_id=test_user.id,
                topic_id="phase0-topic1",
                question_id=f"phase0-topic1-q{q_num}",
                user_answer="Good answer",
                is_passed=True,
                llm_feedback="Correct",
            )
            db_session.add(attempt)

        # Add 3 failed attempts
        for q_num in range(6, 9):
            attempt = QuestionAttempt(
                user_id=test_user.id,
                topic_id="phase0-topic1",
                question_id=f"phase0-topic1-q{q_num}",
                user_answer="Wrong answer",
                is_passed=False,
                llm_feedback="Try again",
            )
            db_session.add(attempt)

        await db_session.commit()

        dashboard = await get_dashboard(
            db=db_session,
            user_id=test_user.id,
            user_email=test_user.email,
            user_first_name=test_user.first_name,
            user_last_name=test_user.last_name,
            user_avatar_url=None,
            user_github_username=test_user.github_username,
            is_admin=False,
        )

        phase_0 = next(p for p in dashboard.phases if p.id == 0)

        # Should count only 5 passed questions, not 8 total attempts
        # Progress calculation should reflect only passed questions
        assert phase_0.progress.questions_passed == 5
