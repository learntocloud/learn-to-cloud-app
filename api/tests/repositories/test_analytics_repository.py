"""Integration tests for AnalyticsRepository.

Tests cover every aggregate query method, including the fix for
active_learners counting submissions alongside step_progress.
"""

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from models import SubmissionType
from repositories.analytics_repository import AnalyticsRepository
from repositories.progress_repository import StepProgressRepository
from repositories.submission_repository import SubmissionRepository
from repositories.user_repository import UserRepository

pytestmark = pytest.mark.integration

# Use high IDs to avoid collisions with other test modules
USER_A = 900001
USER_B = 900002
USER_C = 900003
USER_D = 900004


@pytest.fixture()
async def users(db_session: AsyncSession):
    """Create test users for FK constraints."""
    repo = UserRepository(db_session)
    await repo.upsert(USER_A, github_username="analytics-user-a")
    await repo.upsert(USER_B, github_username="analytics-user-b")
    await repo.upsert(USER_C, github_username="analytics-user-c")
    await repo.upsert(USER_D, github_username="analytics-user-d")
    await db_session.flush()


# =========================================================================
# get_total_users
# =========================================================================


class TestGetTotalUsers:
    async def test_returns_zero_when_empty(self, db_session: AsyncSession):
        repo = AnalyticsRepository(db_session)
        assert await repo.get_total_users() == 0

    async def test_counts_all_users(self, db_session: AsyncSession, users):
        repo = AnalyticsRepository(db_session)
        assert await repo.get_total_users() == 4


# =========================================================================
# get_active_learners — the bug this test suite was created to prevent
# =========================================================================


class TestGetActiveLearners:
    async def test_returns_zero_when_no_activity(self, db_session: AsyncSession, users):
        repo = AnalyticsRepository(db_session)
        assert await repo.get_active_learners(days=30) == 0

    async def test_counts_users_with_step_progress_only(
        self, db_session: AsyncSession, users
    ):
        """Users who only completed reading steps are counted."""
        progress_repo = StepProgressRepository(db_session)
        await progress_repo.create_if_not_exists(USER_A, "topic-1", "step-1", 1, 0)
        await db_session.flush()

        repo = AnalyticsRepository(db_session)
        assert await repo.get_active_learners(days=30) == 1

    async def test_counts_users_with_submissions_only(
        self, db_session: AsyncSession, users
    ):
        """Users who only submitted verifications (no steps) are counted.

        This is the exact scenario that caused the original bug: users
        submitting GitHub profile verification without completing any
        reading steps were invisible to the active_learners metric.
        """
        sub_repo = SubmissionRepository(db_session)
        await sub_repo.create(
            user_id=USER_B,
            requirement_id="github-profile",
            submission_type=SubmissionType.GITHUB_PROFILE,
            phase_id=0,
            submitted_value="https://github.com/testuser",
            extracted_username="testuser",
            is_validated=True,
        )
        await db_session.flush()

        repo = AnalyticsRepository(db_session)
        assert await repo.get_active_learners(days=30) == 1

    async def test_counts_users_with_both_steps_and_submissions(
        self, db_session: AsyncSession, users
    ):
        """Users with both activity types are counted once (not double-counted)."""
        progress_repo = StepProgressRepository(db_session)
        sub_repo = SubmissionRepository(db_session)

        await progress_repo.create_if_not_exists(USER_A, "topic-1", "step-1", 1, 0)
        await sub_repo.create(
            user_id=USER_A,
            requirement_id="github-profile",
            submission_type=SubmissionType.GITHUB_PROFILE,
            phase_id=0,
            submitted_value="https://github.com/testuser",
            extracted_username="testuser",
            is_validated=True,
        )
        await db_session.flush()

        repo = AnalyticsRepository(db_session)
        assert await repo.get_active_learners(days=30) == 1

    async def test_combines_all_activity_types(self, db_session: AsyncSession, users):
        """Mixed scenario: step-only + submission-only + both = correct total."""
        progress_repo = StepProgressRepository(db_session)
        sub_repo = SubmissionRepository(db_session)

        # User A: steps only
        await progress_repo.create_if_not_exists(USER_A, "topic-1", "step-1", 1, 0)
        # User B: submissions only
        await sub_repo.create(
            user_id=USER_B,
            requirement_id="github-profile",
            submission_type=SubmissionType.GITHUB_PROFILE,
            phase_id=0,
            submitted_value="https://github.com/b",
            extracted_username="b",
            is_validated=True,
        )
        # User C: both steps and submissions
        await progress_repo.create_if_not_exists(USER_C, "topic-1", "step-1", 1, 0)
        await sub_repo.create(
            user_id=USER_C,
            requirement_id="github-profile",
            submission_type=SubmissionType.GITHUB_PROFILE,
            phase_id=0,
            submitted_value="https://github.com/c",
            extracted_username="c",
            is_validated=True,
        )
        # User D: no activity (should not count)
        await db_session.flush()

        repo = AnalyticsRepository(db_session)
        assert await repo.get_active_learners(days=30) == 3

    async def test_excludes_activity_outside_window(
        self, db_session: AsyncSession, users
    ):
        """Activity older than the window is excluded."""
        from sqlalchemy import update

        from models import StepProgress

        progress_repo = StepProgressRepository(db_session)
        await progress_repo.create_if_not_exists(USER_A, "topic-1", "step-1", 1, 0)
        await db_session.flush()

        # Backdate the step completion to 60 days ago
        old_date = datetime.now(UTC) - timedelta(days=60)
        await db_session.execute(
            update(StepProgress)
            .where(StepProgress.user_id == USER_A)
            .values(completed_at=old_date)
        )
        await db_session.flush()

        repo = AnalyticsRepository(db_session)
        assert await repo.get_active_learners(days=30) == 0
