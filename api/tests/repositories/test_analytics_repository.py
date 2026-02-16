"""Integration tests for AnalyticsRepository.get_active_learners()."""

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from repositories.analytics_repository import AnalyticsRepository
from repositories.progress_repository import StepProgressRepository
from repositories.user_repository import UserRepository

pytestmark = pytest.mark.integration


@pytest.fixture()
async def users(db_session: AsyncSession):
    """Create test users for FK constraints."""
    repo = UserRepository(db_session)
    user1 = await repo.upsert(90001, github_username="analyticsuser1")
    user2 = await repo.upsert(90002, github_username="analyticsuser2")
    user3 = await repo.upsert(90003, github_username="analyticsuser3")
    return [user1, user2, user3]


class TestGetActiveLearners:
    async def test_counts_users_with_recent_step_completions(
        self, db_session: AsyncSession, users
    ):
        """Users who completed steps in the last 30 days should be counted."""
        # Create step completions for multiple users
        step_repo = StepProgressRepository(db_session)
        await step_repo.create_if_not_exists(90001, "topic-1", "step-1", 1, 1)
        await step_repo.create_if_not_exists(90002, "topic-1", "step-1", 1, 1)
        await step_repo.create_if_not_exists(90003, "topic-2", "step-1", 1, 2)
        await db_session.flush()

        analytics_repo = AnalyticsRepository(db_session)
        active_count = await analytics_repo.get_active_learners(days=30)

        # Should count all 3 distinct users
        assert active_count == 3

    async def test_counts_each_user_once_with_multiple_steps(
        self, db_session: AsyncSession, users
    ):
        """Users with multiple step completions should be counted only once."""
        # User1 completes multiple steps
        step_repo = StepProgressRepository(db_session)
        await step_repo.create_if_not_exists(90001, "topic-1", "step-1", 1, 1)
        await step_repo.create_if_not_exists(90001, "topic-1", "step-2", 2, 1)
        await step_repo.create_if_not_exists(90001, "topic-2", "step-1", 1, 2)
        await db_session.flush()

        analytics_repo = AnalyticsRepository(db_session)
        active_count = await analytics_repo.get_active_learners(days=30)

        # Should count user1 only once despite 3 step completions
        assert active_count == 1

    async def test_excludes_users_with_old_activity(
        self, db_session: AsyncSession, users
    ):
        """Users with activity older than the cutoff should not be counted."""
        step_repo = StepProgressRepository(db_session)

        # Create a step completion with an old timestamp (40 days ago)
        old_progress = await step_repo.create_if_not_exists(
            90001, "topic-1", "step-1", 1, 1
        )
        if old_progress:
            old_progress.completed_at = datetime.now(UTC) - timedelta(days=40)
            db_session.add(old_progress)

        await db_session.flush()

        analytics_repo = AnalyticsRepository(db_session)
        active_count = await analytics_repo.get_active_learners(days=30)

        # Should not count user with old activity
        assert active_count == 0

    async def test_includes_recent_and_excludes_old(
        self, db_session: AsyncSession, users
    ):
        """Should count only users with recent activity."""
        step_repo = StepProgressRepository(db_session)

        # User1: recent activity (within 30 days)
        await step_repo.create_if_not_exists(90001, "topic-1", "step-1", 1, 1)

        # User2: old activity (40 days ago)
        old_progress = await step_repo.create_if_not_exists(
            90002, "topic-1", "step-1", 1, 1
        )
        if old_progress:
            old_progress.completed_at = datetime.now(UTC) - timedelta(days=40)
            db_session.add(old_progress)

        # User3: recent activity
        await step_repo.create_if_not_exists(90003, "topic-1", "step-1", 1, 1)

        await db_session.flush()

        analytics_repo = AnalyticsRepository(db_session)
        active_count = await analytics_repo.get_active_learners(days=30)

        # Should count only user1 and user3
        assert active_count == 2

    async def test_respects_custom_day_range(self, db_session: AsyncSession, users):
        """Should respect custom day range parameter."""
        step_repo = StepProgressRepository(db_session)

        # Create activity 20 days ago
        progress = await step_repo.create_if_not_exists(90001, "topic-1", "step-1", 1, 1)
        if progress:
            progress.completed_at = datetime.now(UTC) - timedelta(days=20)
            db_session.add(progress)

        await db_session.flush()

        analytics_repo = AnalyticsRepository(db_session)

        # Should be counted in 30-day window
        count_30d = await analytics_repo.get_active_learners(days=30)
        assert count_30d == 1

        # Should not be counted in 15-day window
        count_15d = await analytics_repo.get_active_learners(days=15)
        assert count_15d == 0

    async def test_returns_zero_for_no_activity(self, db_session: AsyncSession, users):
        """Should return 0 when there's no recent activity."""
        analytics_repo = AnalyticsRepository(db_session)
        active_count = await analytics_repo.get_active_learners(days=30)

        assert active_count == 0
