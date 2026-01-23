"""Tests for ActivityRepository.

Tests database operations for user activity tracking and streak calculation.
"""

from datetime import date, timedelta

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

# Mark all tests in this module as integration tests (database required)
pytestmark = pytest.mark.integration

from models import ActivityType
from repositories.activity_repository import ActivityRepository
from tests.factories import (
    UserActivityFactory,
    UserFactory,
    create_async,
)


class TestActivityRepositoryGetByUser:
    """Tests for ActivityRepository.get_by_user()."""

    async def test_returns_activities_ordered_by_date_desc(
        self, db_session: AsyncSession
    ):
        """Should return activities ordered by created_at descending."""
        user = await create_async(UserFactory, db_session)
        today = date.today()

        # Create activities in non-sequential order
        activity_older = await create_async(
            UserActivityFactory,
            db_session,
            user_id=user.id,
            activity_date=today - timedelta(days=2),
        )
        activity_newer = await create_async(
            UserActivityFactory,
            db_session,
            user_id=user.id,
            activity_date=today,
        )

        repo = ActivityRepository(db_session)

        result = await repo.get_by_user(user.id)

        assert len(result) == 2
        assert result[0].id == activity_newer.id
        assert result[1].id == activity_older.id

    async def test_respects_limit(self, db_session: AsyncSession):
        """Should limit number of results when limit is provided."""
        user = await create_async(UserFactory, db_session)
        for i in range(5):
            await create_async(
                UserActivityFactory,
                db_session,
                user_id=user.id,
                activity_date=date.today() - timedelta(days=i),
            )

        repo = ActivityRepository(db_session)

        result = await repo.get_by_user(user.id, limit=3)

        assert len(result) == 3

    async def test_cursor_pagination(self, db_session: AsyncSession):
        """Should paginate using cursor (activity ID)."""
        user = await create_async(UserFactory, db_session)
        activities = []
        for i in range(5):
            a = await create_async(
                UserActivityFactory,
                db_session,
                user_id=user.id,
                activity_date=date.today() - timedelta(days=i),
            )
            activities.append(a)

        repo = ActivityRepository(db_session)

        # Get first page
        page1 = await repo.get_by_user(user.id, limit=2)
        assert len(page1) == 2

        # Get second page using cursor
        cursor = page1[-1].id
        page2 = await repo.get_by_user(user.id, limit=2, cursor=cursor)

        # Should not overlap
        page1_ids = {a.id for a in page1}
        page2_ids = {a.id for a in page2}
        assert page1_ids.isdisjoint(page2_ids)


class TestActivityRepositoryLogActivity:
    """Tests for ActivityRepository.log_activity()."""

    async def test_creates_activity(self, db_session: AsyncSession):
        """Should create a new activity record."""
        user = await create_async(UserFactory, db_session)
        repo = ActivityRepository(db_session)

        activity = await repo.log_activity(
            user_id=user.id,
            activity_type=ActivityType.STEP_COMPLETE,
            activity_date=date.today(),
            reference_id="phase1-topic1",
        )

        assert activity.user_id == user.id
        assert activity.activity_type == ActivityType.STEP_COMPLETE
        assert activity.reference_id == "phase1-topic1"

    async def test_allows_multiple_activities_same_day(self, db_session: AsyncSession):
        """Should allow multiple activities on the same day."""
        user = await create_async(UserFactory, db_session)
        repo = ActivityRepository(db_session)
        today = date.today()

        activity1 = await repo.log_activity(
            user_id=user.id,
            activity_type=ActivityType.STEP_COMPLETE,
            activity_date=today,
        )
        activity2 = await repo.log_activity(
            user_id=user.id,
            activity_type=ActivityType.QUESTION_ATTEMPT,
            activity_date=today,
        )

        assert activity1.id != activity2.id


class TestActivityRepositoryHasActivityOnDate:
    """Tests for ActivityRepository.has_activity_on_date()."""

    async def test_returns_true_when_has_activity(self, db_session: AsyncSession):
        """Should return True when user has activity on date."""
        user = await create_async(UserFactory, db_session)
        today = date.today()
        await create_async(
            UserActivityFactory,
            db_session,
            user_id=user.id,
            activity_date=today,
        )
        repo = ActivityRepository(db_session)

        result = await repo.has_activity_on_date(user.id, today)

        assert result is True

    async def test_returns_false_when_no_activity(self, db_session: AsyncSession):
        """Should return False when user has no activity on date."""
        user = await create_async(UserFactory, db_session)
        repo = ActivityRepository(db_session)

        result = await repo.has_activity_on_date(user.id, date.today())

        assert result is False


class TestActivityRepositoryGetActivityDatesOrdered:
    """Tests for ActivityRepository.get_activity_dates_ordered()."""

    async def test_returns_distinct_dates_ordered_desc(self, db_session: AsyncSession):
        """Should return distinct activity dates in descending order."""
        user = await create_async(UserFactory, db_session)
        today = date.today()

        # Create multiple activities on same day and different days
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
            activity_date=today,  # Duplicate date
        )
        await create_async(
            UserActivityFactory,
            db_session,
            user_id=user.id,
            activity_date=today - timedelta(days=1),
        )

        repo = ActivityRepository(db_session)

        result = await repo.get_activity_dates_ordered(user.id)

        assert len(result) == 2  # Distinct dates only
        assert result[0] == today
        assert result[1] == today - timedelta(days=1)

    async def test_respects_limit(self, db_session: AsyncSession):
        """Should limit number of dates returned."""
        user = await create_async(UserFactory, db_session)
        for i in range(10):
            await create_async(
                UserActivityFactory,
                db_session,
                user_id=user.id,
                activity_date=date.today() - timedelta(days=i),
            )

        repo = ActivityRepository(db_session)

        result = await repo.get_activity_dates_ordered(user.id, limit=5)

        assert len(result) == 5


class TestActivityRepositoryCountByType:
    """Tests for ActivityRepository.count_by_type()."""

    async def test_counts_activities_of_specific_type(self, db_session: AsyncSession):
        """Should count only activities of specified type."""
        user = await create_async(UserFactory, db_session)

        # Create mixed activity types
        for _ in range(3):
            await create_async(
                UserActivityFactory,
                db_session,
                user_id=user.id,
                activity_type=ActivityType.STEP_COMPLETE,
            )
        for _ in range(2):
            await create_async(
                UserActivityFactory,
                db_session,
                user_id=user.id,
                activity_type=ActivityType.QUESTION_ATTEMPT,
            )

        repo = ActivityRepository(db_session)

        step_count = await repo.count_by_type(user.id, ActivityType.STEP_COMPLETE)
        question_count = await repo.count_by_type(
            user.id, ActivityType.QUESTION_ATTEMPT
        )

        assert step_count == 3
        assert question_count == 2


class TestActivityRepositoryGetActivitiesInRange:
    """Tests for ActivityRepository.get_activities_in_range()."""

    async def test_returns_activities_within_date_range(self, db_session: AsyncSession):
        """Should return only activities within specified date range."""
        user = await create_async(UserFactory, db_session)
        today = date.today()

        # Create activities spanning multiple days
        in_range_1 = await create_async(
            UserActivityFactory,
            db_session,
            user_id=user.id,
            activity_date=today - timedelta(days=5),
        )
        in_range_2 = await create_async(
            UserActivityFactory,
            db_session,
            user_id=user.id,
            activity_date=today - timedelta(days=3),
        )
        await create_async(
            UserActivityFactory,
            db_session,
            user_id=user.id,
            activity_date=today - timedelta(days=10),  # Out of range
        )

        repo = ActivityRepository(db_session)

        result = await repo.get_activities_in_range(
            user.id,
            start_date=today - timedelta(days=7),
            end_date=today,
        )

        assert len(result) == 2
        result_ids = {a.id for a in result}
        assert in_range_1.id in result_ids
        assert in_range_2.id in result_ids


class TestActivityRepositoryGetHeatmapData:
    """Tests for ActivityRepository.get_heatmap_data()."""

    async def test_returns_grouped_activity_counts(self, db_session: AsyncSession):
        """Should return activity counts grouped by date and type."""
        user = await create_async(UserFactory, db_session)
        today = date.today()

        # Create activities
        for _ in range(3):
            await create_async(
                UserActivityFactory,
                db_session,
                user_id=user.id,
                activity_type=ActivityType.STEP_COMPLETE,
                activity_date=today,
            )
        await create_async(
            UserActivityFactory,
            db_session,
            user_id=user.id,
            activity_type=ActivityType.QUESTION_ATTEMPT,
            activity_date=today,
        )

        repo = ActivityRepository(db_session)

        result = await repo.get_heatmap_data(
            user.id,
            start_date=today - timedelta(days=7),
        )

        # Convert to dict for easier assertion
        # Note: activity_type is ActivityType enum, need to handle it
        data = {
            (d, t.value if hasattr(t, "value") else str(t)): c for d, t, c in result
        }

        assert data.get((today, "step_complete")) == 3
        assert data.get((today, "question_attempt")) == 1
