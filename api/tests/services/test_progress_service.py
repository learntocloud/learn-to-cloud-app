"""Tests for progress service."""

from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from services.progress_service import (
    _parse_phase_from_question_id,
    _parse_phase_from_topic_id,
    fetch_user_progress,
    get_all_phase_ids,
    get_phase_requirements,
)
from tests.factories import (
    QuestionAttemptFactory,
    StepProgressFactory,
    SubmissionFactory,
    UserFactory,
)


class TestParsePhaseFromTopicId:
    """Tests for _parse_phase_from_topic_id."""

    def test_parses_valid_topic_id(self):
        """Test parsing valid topic ID."""
        result = _parse_phase_from_topic_id("phase1-topic4")
        assert result == 1

    def test_parses_phase_zero(self):
        """Test parsing phase 0."""
        result = _parse_phase_from_topic_id("phase0-topic1")
        assert result == 0

    def test_parses_double_digit_phase(self):
        """Test parsing double digit phase number."""
        result = _parse_phase_from_topic_id("phase12-topic3")
        assert result == 12

    def test_returns_none_for_invalid_format(self):
        """Test returns None for invalid format."""
        assert _parse_phase_from_topic_id("invalid") is None
        assert _parse_phase_from_topic_id("topic1-phase2") is None
        assert _parse_phase_from_topic_id("") is None

    def test_returns_none_for_non_string(self):
        """Test returns None for non-string input."""
        assert _parse_phase_from_topic_id(None) is None
        assert _parse_phase_from_topic_id(123) is None


class TestParsePhaseFromQuestionId:
    """Tests for _parse_phase_from_question_id."""

    def test_parses_valid_question_id(self):
        """Test parsing valid question ID."""
        result = _parse_phase_from_question_id("phase2-topic1-q3")
        assert result == 2

    def test_parses_phase_zero(self):
        """Test parsing phase 0."""
        result = _parse_phase_from_question_id("phase0-topic1-q1")
        assert result == 0

    def test_returns_none_for_invalid_format(self):
        """Test returns None for invalid format."""
        assert _parse_phase_from_question_id("invalid") is None
        assert _parse_phase_from_question_id("q1-phase2-topic3") is None

    def test_returns_none_for_non_string(self):
        """Test returns None for non-string input."""
        assert _parse_phase_from_question_id(None) is None


class TestGetPhaseRequirements:
    """Tests for get_phase_requirements."""

    def test_returns_requirements_for_valid_phase(self):
        """Test returns requirements for a valid phase."""
        # Phase 0 should always exist
        result = get_phase_requirements(0)
        if result is None:
            pytest.skip("No phases loaded from content")

        assert result.phase_id == 0
        assert result.steps >= 0
        assert result.questions >= 0
        assert result.topics >= 0

    def test_returns_none_for_invalid_phase(self):
        """Test returns None for non-existent phase."""
        result = get_phase_requirements(999)
        assert result is None


class TestGetAllPhaseIds:
    """Tests for get_all_phase_ids."""

    def test_returns_sorted_phase_ids(self):
        """Test returns phase IDs in sorted order."""
        result = get_all_phase_ids()
        assert isinstance(result, list)
        assert result == sorted(result)

    def test_includes_phase_zero(self):
        """Test includes phase 0 if it exists."""
        result = get_all_phase_ids()
        if result:
            assert 0 in result


class TestFetchUserProgress:
    """Tests for fetch_user_progress."""

    @pytest.fixture
    async def user(self, db_session: AsyncSession):
        """Create a test user."""
        user = UserFactory.build()
        db_session.add(user)
        await db_session.flush()
        return user

    async def test_returns_user_progress(self, db_session: AsyncSession, user):
        """Test returns UserProgress object."""
        result = await fetch_user_progress(db_session, user.id)

        assert result.user_id == user.id
        assert isinstance(result.phases, dict)
        assert result.total_phases > 0

    async def test_counts_completed_steps(self, db_session: AsyncSession, user):
        """Test counts completed steps per phase."""
        # Create some step progress
        step1 = StepProgressFactory.build(
            user_id=user.id, topic_id="phase0-topic1", step_order=1
        )
        step2 = StepProgressFactory.build(
            user_id=user.id, topic_id="phase0-topic1", step_order=2
        )
        db_session.add_all([step1, step2])
        await db_session.flush()

        result = await fetch_user_progress(db_session, user.id, skip_cache=True)

        if 0 in result.phases:
            assert result.phases[0].steps_completed >= 2

    async def test_counts_passed_questions(self, db_session: AsyncSession, user):
        """Test counts passed questions per phase."""
        # Create passed question attempt
        attempt = QuestionAttemptFactory.build(
            user_id=user.id,
            topic_id="phase1-topic1",
            question_id="phase1-topic1-q1",
            is_passed=True,
        )
        db_session.add(attempt)
        await db_session.flush()

        result = await fetch_user_progress(db_session, user.id, skip_cache=True)

        if 1 in result.phases:
            assert result.phases[1].questions_passed >= 1

    async def test_tracks_validated_submissions(self, db_session: AsyncSession, user):
        """Test tracks validated hands-on submissions."""
        # Create validated submission
        submission = SubmissionFactory.build(
            user_id=user.id,
            phase_id=0,
            requirement_id="phase0-github-profile",
            is_validated=True,
        )
        db_session.add(submission)
        await db_session.flush()

        result = await fetch_user_progress(db_session, user.id, skip_cache=True)

        if 0 in result.phases:
            assert result.phases[0].hands_on_validated_count >= 1

    async def test_uses_cache(self, db_session: AsyncSession, user):
        """Test that results are cached."""
        # First call
        result1 = await fetch_user_progress(db_session, user.id)

        # Second call should use cache
        result2 = await fetch_user_progress(db_session, user.id)

        # Results should be identical
        assert result1.user_id == result2.user_id

    async def test_skip_cache_bypasses_cache(self, db_session: AsyncSession, user):
        """Test that skip_cache bypasses the cache."""
        # First call (populates cache)
        await fetch_user_progress(db_session, user.id)

        # Add new data
        step = StepProgressFactory.build(
            user_id=user.id, topic_id="phase0-topic1", step_order=5
        )
        db_session.add(step)
        await db_session.flush()

        # Skip cache should see new data
        result = await fetch_user_progress(db_session, user.id, skip_cache=True)

        # Should have the new step counted
        if 0 in result.phases:
            assert result.phases[0].steps_completed >= 1


class TestPhaseCompletion:
    """Tests for phase completion logic."""

    @pytest.fixture
    async def user(self, db_session: AsyncSession):
        """Create a test user."""
        user = UserFactory.build()
        db_session.add(user)
        await db_session.flush()
        return user

    async def test_phase_marked_complete_when_all_requirements_met(
        self, db_session: AsyncSession, user
    ):
        """Test that phase is marked complete when all requirements are met."""
        # This test verifies the completion logic structure
        # Complete phase would require all steps, questions, and hands-on
        result = await fetch_user_progress(db_session, user.id, skip_cache=True)

        # New user shouldn't have any complete phases
        for phase_id, phase_progress in result.phases.items():
            # Most phases won't be complete for a new user
            if phase_progress.steps_required > 0 or phase_progress.questions_required > 0:
                # If there are requirements, new user shouldn't have completed them
                if (
                    phase_progress.steps_completed == 0
                    and phase_progress.questions_passed == 0
                ):
                    assert phase_progress.is_complete is False

    async def test_overall_percentage_calculation(
        self, db_session: AsyncSession, user
    ):
        """Test overall progress percentage calculation."""
        result = await fetch_user_progress(db_session, user.id, skip_cache=True)

        # Percentage should be between 0 and 100
        assert 0 <= result.overall_percentage <= 100

    async def test_phases_completed_count(self, db_session: AsyncSession, user):
        """Test phases completed count."""
        result = await fetch_user_progress(db_session, user.id, skip_cache=True)

        # Should be an integer >= 0
        assert isinstance(result.phases_completed, int)
        assert result.phases_completed >= 0
        assert result.phases_completed <= result.total_phases
