"""Integration tests for AnalyticsRepository."""

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from models import SubmissionType
from repositories.analytics_repository import AnalyticsRepository
from repositories.progress_repository import StepProgressRepository
from repositories.submission_repository import SubmissionRepository
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
        # Create step completion for user1 within the last 30 days
        step_repo = StepProgressRepository(db_session)
        await step_repo.create_if_not_exists(90001, "topic-1", "step-1", 1, 1)
        await db_session.flush()

        analytics_repo = AnalyticsRepository(db_session)
        active_count = await analytics_repo.get_active_learners(days=30)

        assert active_count == 1

    async def test_counts_users_with_recent_submissions(
        self, db_session: AsyncSession, users
    ):
        """Users who created submissions in the last 30 days should be counted."""
        # Create submission for user2 within the last 30 days
        sub_repo = SubmissionRepository(db_session)
        await sub_repo.create(
            user_id=90002,
            requirement_id="req-1",
            submission_type=SubmissionType.GITHUB_PROFILE,
            phase_id=0,
            submitted_value="https://github.com/user2",
            extracted_username="user2",
            is_validated=True,
        )
        await db_session.flush()

        analytics_repo = AnalyticsRepository(db_session)
        active_count = await analytics_repo.get_active_learners(days=30)

        assert active_count == 1

    async def test_counts_users_with_both_steps_and_submissions(
        self, db_session: AsyncSession, users
    ):
        """Users with both step completions and submissions should be counted once."""
        # User1: has both step completion and submission
        step_repo = StepProgressRepository(db_session)
        await step_repo.create_if_not_exists(90001, "topic-1", "step-1", 1, 1)

        sub_repo = SubmissionRepository(db_session)
        await sub_repo.create(
            user_id=90001,
            requirement_id="req-1",
            submission_type=SubmissionType.GITHUB_PROFILE,
            phase_id=0,
            submitted_value="https://github.com/user1",
            extracted_username="user1",
            is_validated=True,
        )
        await db_session.flush()

        analytics_repo = AnalyticsRepository(db_session)
        active_count = await analytics_repo.get_active_learners(days=30)

        # Should count user1 only once despite having both activities
        assert active_count == 1

    async def test_counts_distinct_users_with_multiple_activities(
        self, db_session: AsyncSession, users
    ):
        """Multiple users with different activity types should all be counted."""
        step_repo = StepProgressRepository(db_session)
        sub_repo = SubmissionRepository(db_session)

        # User1: step completion only
        await step_repo.create_if_not_exists(90001, "topic-1", "step-1", 1, 1)

        # User2: submission only
        await sub_repo.create(
            user_id=90002,
            requirement_id="req-1",
            submission_type=SubmissionType.GITHUB_PROFILE,
            phase_id=0,
            submitted_value="https://github.com/user2",
            extracted_username="user2",
            is_validated=True,
        )

        # User3: both step and submission
        await step_repo.create_if_not_exists(90003, "topic-1", "step-1", 1, 1)
        await sub_repo.create(
            user_id=90003,
            requirement_id="req-2",
            submission_type=SubmissionType.CTF_TOKEN,
            phase_id=1,
            submitted_value="token123",
            extracted_username=None,
            is_validated=False,
        )
        await db_session.flush()

        analytics_repo = AnalyticsRepository(db_session)
        active_count = await analytics_repo.get_active_learners(days=30)

        # Should count all 3 users
        assert active_count == 3

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
