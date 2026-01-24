"""Tests for activity_service.

Tests streak calculation, heatmap generation, and activity logging.
These tests use real database (via fixtures) for accuracy.
"""

from datetime import UTC, date, datetime, timedelta

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from models import ActivityType
from services.activity_service import (
    get_heatmap_data,
    get_streak_data,
    log_activity,
)
from tests.factories import UserActivityFactory, UserFactory, create_async

# Mark all tests in this module as integration tests (database required)
pytestmark = pytest.mark.integration


class TestGetStreakData:
    """Tests for get_streak_data()."""

    async def test_returns_zero_streak_for_new_user(self, db_session: AsyncSession):
        """Should return zero streak for user with no activities."""
        user = await create_async(UserFactory, db_session)

        result = await get_streak_data(db_session, user.id)

        assert result.current_streak == 0
        assert result.longest_streak == 0
        assert result.total_activity_days == 0
        assert result.streak_alive is False

    async def test_returns_active_streak_for_today_activity(
        self, db_session: AsyncSession
    ):
        """Should return active streak when user has activity today."""
        user = await create_async(UserFactory, db_session)
        await create_async(
            UserActivityFactory,
            db_session,
            user_id=user.id,
            activity_date=date.today(),
        )

        result = await get_streak_data(db_session, user.id)

        assert result.current_streak == 1
        assert result.longest_streak == 1
        assert result.streak_alive is True

    async def test_streak_survives_one_day_gap(self, db_session: AsyncSession):
        """Should maintain streak with 1 day gap (forgiveness)."""
        user = await create_async(UserFactory, db_session)
        today = date.today()

        # Activity today and 2 days ago (1 day gap)
        await create_async(
            UserActivityFactory,
            db_session,
            user_id=user.id,
            activity_date=today,
        )
        await create_async(
            UserActivityFactory,
            db_session,
            user_id=user.id,
            activity_date=today - timedelta(days=2),
        )

        result = await get_streak_data(db_session, user.id)

        assert result.current_streak == 2
        assert result.streak_alive is True

    async def test_streak_survives_two_day_gap(self, db_session: AsyncSession):
        """Should maintain streak with 2 day gap (max forgiveness)."""
        user = await create_async(UserFactory, db_session)
        today = date.today()

        # Activity today and 3 days ago (2 day gap)
        await create_async(
            UserActivityFactory,
            db_session,
            user_id=user.id,
            activity_date=today,
        )
        await create_async(
            UserActivityFactory,
            db_session,
            user_id=user.id,
            activity_date=today - timedelta(days=3),
        )

        result = await get_streak_data(db_session, user.id)

        assert result.current_streak == 2
        assert result.streak_alive is True

    async def test_streak_breaks_after_three_day_gap(self, db_session: AsyncSession):
        """Should break streak with 3+ day gap."""
        user = await create_async(UserFactory, db_session)
        today = date.today()

        # Activity today and 4 days ago (3 day gap = broken)
        await create_async(
            UserActivityFactory,
            db_session,
            user_id=user.id,
            activity_date=today,
        )
        await create_async(
            UserActivityFactory,
            db_session,
            user_id=user.id,
            activity_date=today - timedelta(days=4),
        )

        result = await get_streak_data(db_session, user.id)

        assert result.current_streak == 1  # Only today counts
        assert result.longest_streak == 1  # Both segments are length 1
        assert result.streak_alive is True

    async def test_preserves_longest_streak(self, db_session: AsyncSession):
        """Should preserve longest streak even when current is broken."""
        user = await create_async(UserFactory, db_session)
        today = date.today()

        # Old streak: 5 consecutive days
        for i in range(5):
            await create_async(
                UserActivityFactory,
                db_session,
                user_id=user.id,
                activity_date=today - timedelta(days=20 + i),
            )

        # Big gap, then activity today
        await create_async(
            UserActivityFactory,
            db_session,
            user_id=user.id,
            activity_date=today,
        )

        result = await get_streak_data(db_session, user.id)

        assert result.current_streak == 1  # New streak
        assert result.longest_streak == 5  # Old streak preserved
        assert result.streak_alive is True

    async def test_streak_dead_if_no_recent_activity(self, db_session: AsyncSession):
        """Should mark streak as dead if last activity > 2 days ago."""
        user = await create_async(UserFactory, db_session)
        today = date.today()

        # Activity 4 days ago (beyond forgiveness window)
        await create_async(
            UserActivityFactory,
            db_session,
            user_id=user.id,
            activity_date=today - timedelta(days=4),
        )

        result = await get_streak_data(db_session, user.id)

        assert result.current_streak == 0  # Dead
        assert result.longest_streak == 1  # Had a 1-day streak
        assert result.streak_alive is False


class TestGetHeatmapData:
    """Tests for get_heatmap_data()."""

    async def test_returns_empty_heatmap_for_new_user(self, db_session: AsyncSession):
        """Should return empty heatmap for user with no activities."""
        user = await create_async(UserFactory, db_session)

        result = await get_heatmap_data(db_session, user.id, days=30)

        assert result.days == []
        assert result.total_activities == 0

    async def test_aggregates_activities_by_date(self, db_session: AsyncSession):
        """Should aggregate multiple activities on same date."""
        user = await create_async(UserFactory, db_session)
        today = date.today()

        # Multiple activities on same day
        for _ in range(3):
            await create_async(
                UserActivityFactory,
                db_session,
                user_id=user.id,
                activity_date=today,
                activity_type=ActivityType.STEP_COMPLETE,
            )

        result = await get_heatmap_data(db_session, user.id, days=30)

        assert len(result.days) == 1
        assert result.days[0].date == today
        assert result.days[0].count == 3
        assert result.total_activities == 3

    async def test_includes_multiple_activity_types(self, db_session: AsyncSession):
        """Should include all activity types in heatmap day."""
        user = await create_async(UserFactory, db_session)
        today = date.today()

        await create_async(
            UserActivityFactory,
            db_session,
            user_id=user.id,
            activity_date=today,
            activity_type=ActivityType.STEP_COMPLETE,
        )
        await create_async(
            UserActivityFactory,
            db_session,
            user_id=user.id,
            activity_date=today,
            activity_type=ActivityType.QUESTION_ATTEMPT,
        )

        result = await get_heatmap_data(db_session, user.id, days=30)

        assert len(result.days) == 1
        activity_types = {
            t.value if hasattr(t, "value") else str(t)
            for t in result.days[0].activity_types
        }
        assert "step_complete" in activity_types
        assert "question_attempt" in activity_types

    async def test_respects_days_parameter(self, db_session: AsyncSession):
        """Should only include activities within specified days."""
        user = await create_async(UserFactory, db_session)
        today = date.today()

        # Activity within range
        await create_async(
            UserActivityFactory,
            db_session,
            user_id=user.id,
            activity_date=today - timedelta(days=5),
        )
        # Activity outside range
        await create_async(
            UserActivityFactory,
            db_session,
            user_id=user.id,
            activity_date=today - timedelta(days=15),
        )

        result = await get_heatmap_data(db_session, user.id, days=10)

        assert result.total_activities == 1


class TestLogActivity:
    """Tests for log_activity()."""

    async def test_logs_activity(self, db_session: AsyncSession):
        """Should log a new activity."""
        user = await create_async(UserFactory, db_session)

        result = await log_activity(
            db_session,
            user.id,
            ActivityType.STEP_COMPLETE,
            reference_id="phase1-topic1",
        )

        assert result.activity_type == ActivityType.STEP_COMPLETE
        assert result.reference_id == "phase1-topic1"
        # Activity uses UTC date, so compare with UTC today
        utc_today = datetime.now(UTC).date()
        assert result.activity_date == utc_today

    async def test_logs_activity_without_reference(self, db_session: AsyncSession):
        """Should log activity without reference_id."""
        user = await create_async(UserFactory, db_session)

        result = await log_activity(
            db_session,
            user.id,
            ActivityType.QUESTION_ATTEMPT,
        )

        assert result.activity_type == ActivityType.QUESTION_ATTEMPT
        assert result.reference_id is None

    async def test_allows_multiple_activities_same_day(self, db_session: AsyncSession):
        """Should allow logging multiple activities on same day."""
        user = await create_async(UserFactory, db_session)

        result1 = await log_activity(db_session, user.id, ActivityType.STEP_COMPLETE)
        result2 = await log_activity(db_session, user.id, ActivityType.QUESTION_ATTEMPT)

        assert result1.id != result2.id
