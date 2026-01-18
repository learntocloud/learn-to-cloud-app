"""Integration tests for repositories/activity_repository.py.

Uses real PostgreSQL database with transaction rollback for isolation.
"""

from datetime import date, timedelta

import pytest

from models import ActivityType, User
from repositories.activity_repository import ActivityRepository


@pytest.mark.asyncio
class TestActivityRepositoryIntegration:
    """Integration tests for ActivityRepository using real PostgreSQL."""

    async def _create_user(self, db, user_id: str = "test-user") -> User:
        """Helper to create a user."""
        user = User(
            id=user_id,
            email=f"{user_id}@example.com",
            first_name="Test",
            last_name="User",
        )
        db.add(user)
        await db.flush()
        return user

    async def test_log_activity_creates_record(self, db_session):
        """log_activity creates new activity record."""
        await self._create_user(db_session)
        repo = ActivityRepository(db_session)

        activity = await repo.log_activity(
            user_id="test-user",
            activity_type=ActivityType.STEP_COMPLETE,
            activity_date=date.today(),
            reference_id="phase0-topic1-step1",
        )

        assert activity.id is not None
        assert activity.user_id == "test-user"
        assert activity.activity_type == ActivityType.STEP_COMPLETE

    async def test_get_by_user_returns_activities(self, db_session):
        """get_by_user returns user's activities in descending order."""
        await self._create_user(db_session)
        repo = ActivityRepository(db_session)

        # Create multiple activities
        await repo.log_activity("test-user", ActivityType.STEP_COMPLETE, date.today())
        await repo.log_activity(
            "test-user", ActivityType.QUESTION_ATTEMPT, date.today()
        )

        activities = await repo.get_by_user("test-user")

        assert len(activities) == 2

    async def test_get_by_user_with_limit(self, db_session):
        """get_by_user respects limit parameter."""
        await self._create_user(db_session)
        repo = ActivityRepository(db_session)

        # Create 5 activities
        for i in range(5):
            await repo.log_activity(
                "test-user", ActivityType.STEP_COMPLETE, date.today()
            )

        activities = await repo.get_by_user("test-user", limit=3)

        assert len(activities) == 3

    async def test_get_by_user_with_pagination_cursor(self, db_session):
        """get_by_user supports cursor-based pagination."""
        await self._create_user(db_session)
        repo = ActivityRepository(db_session)

        # Create activities
        activities_created = []
        for i in range(5):
            a = await repo.log_activity(
                "test-user", ActivityType.STEP_COMPLETE, date.today()
            )
            activities_created.append(a)

        # Get first page
        page1 = await repo.get_by_user("test-user", limit=2)
        assert len(page1) == 2

        # Get second page using cursor
        cursor = page1[-1].id
        page2 = await repo.get_by_user("test-user", limit=2, cursor=cursor)
        assert len(page2) == 2
        # Verify different activities
        assert page1[0].id != page2[0].id

    async def test_get_activities_in_range(self, db_session):
        """get_activities_in_range returns activities within date range."""
        await self._create_user(db_session)
        repo = ActivityRepository(db_session)

        today = date.today()
        yesterday = today - timedelta(days=1)
        two_days_ago = today - timedelta(days=2)
        week_ago = today - timedelta(days=7)

        await repo.log_activity("test-user", ActivityType.STEP_COMPLETE, today)
        await repo.log_activity("test-user", ActivityType.STEP_COMPLETE, yesterday)
        await repo.log_activity("test-user", ActivityType.STEP_COMPLETE, two_days_ago)
        await repo.log_activity("test-user", ActivityType.STEP_COMPLETE, week_ago)

        # Get last 3 days
        activities = await repo.get_activities_in_range(
            "test-user", two_days_ago, today
        )

        assert len(activities) == 3

    async def test_count_by_type(self, db_session):
        """count_by_type counts activities of specific type."""
        await self._create_user(db_session)
        repo = ActivityRepository(db_session)

        await repo.log_activity("test-user", ActivityType.STEP_COMPLETE, date.today())
        await repo.log_activity("test-user", ActivityType.STEP_COMPLETE, date.today())
        await repo.log_activity(
            "test-user", ActivityType.QUESTION_ATTEMPT, date.today()
        )

        step_count = await repo.count_by_type("test-user", ActivityType.STEP_COMPLETE)
        question_count = await repo.count_by_type(
            "test-user", ActivityType.QUESTION_ATTEMPT
        )

        assert step_count == 2
        assert question_count == 1

    async def test_has_activity_on_date_true(self, db_session):
        """has_activity_on_date returns True when activity exists."""
        await self._create_user(db_session)
        repo = ActivityRepository(db_session)

        today = date.today()
        await repo.log_activity("test-user", ActivityType.STEP_COMPLETE, today)

        has_activity = await repo.has_activity_on_date("test-user", today)

        assert has_activity is True

    async def test_has_activity_on_date_false(self, db_session):
        """has_activity_on_date returns False when no activity."""
        await self._create_user(db_session)
        repo = ActivityRepository(db_session)

        # No activities logged
        has_activity = await repo.has_activity_on_date("test-user", date.today())

        assert has_activity is False

    async def test_get_activity_dates_ordered(self, db_session):
        """get_activity_dates_ordered returns dates in descending order."""
        await self._create_user(db_session)
        repo = ActivityRepository(db_session)

        today = date.today()
        yesterday = today - timedelta(days=1)
        two_days_ago = today - timedelta(days=2)

        await repo.log_activity("test-user", ActivityType.STEP_COMPLETE, two_days_ago)
        await repo.log_activity("test-user", ActivityType.STEP_COMPLETE, yesterday)
        await repo.log_activity("test-user", ActivityType.STEP_COMPLETE, today)

        dates = await repo.get_activity_dates_ordered("test-user")

        assert dates == [today, yesterday, two_days_ago]

    async def test_get_activity_dates_ordered_with_limit(self, db_session):
        """get_activity_dates_ordered respects limit."""
        await self._create_user(db_session)
        repo = ActivityRepository(db_session)

        today = date.today()
        for i in range(10):
            await repo.log_activity(
                "test-user",
                ActivityType.STEP_COMPLETE,
                today - timedelta(days=i),
            )

        dates = await repo.get_activity_dates_ordered("test-user", limit=5)

        assert len(dates) == 5

    async def test_get_heatmap_data(self, db_session):
        """get_heatmap_data returns grouped activity counts."""
        await self._create_user(db_session)
        repo = ActivityRepository(db_session)

        today = date.today()
        start_date = today - timedelta(days=7)

        # Create activities of different types on same day
        await repo.log_activity("test-user", ActivityType.STEP_COMPLETE, today)
        await repo.log_activity("test-user", ActivityType.STEP_COMPLETE, today)
        await repo.log_activity("test-user", ActivityType.QUESTION_ATTEMPT, today)

        heatmap = await repo.get_heatmap_data("test-user", start_date)

        # Should have 2 rows:
        # - one for STEP_COMPLETE (count=2)
        # - one for QUESTION_ATTEMPT (count=1)
        assert len(heatmap) == 2

        # Find the step complete row
        step_row = next(r for r in heatmap if r[1] == ActivityType.STEP_COMPLETE)
        assert step_row[2] == 2  # count

    async def test_isolation_between_users(self, db_session):
        """Activities are isolated between users."""
        await self._create_user(db_session, "user-1")
        await self._create_user(db_session, "user-2")
        repo = ActivityRepository(db_session)

        await repo.log_activity("user-1", ActivityType.STEP_COMPLETE, date.today())
        await repo.log_activity("user-1", ActivityType.STEP_COMPLETE, date.today())
        await repo.log_activity("user-2", ActivityType.STEP_COMPLETE, date.today())

        user1_activities = await repo.get_by_user("user-1")
        user2_activities = await repo.get_by_user("user-2")

        assert len(user1_activities) == 2
        assert len(user2_activities) == 1
