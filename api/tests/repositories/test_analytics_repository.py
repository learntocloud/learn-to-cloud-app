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


# =========================================================================
# get_step_completion_histogram
# =========================================================================


class TestGetStepCompletionHistogram:
    async def test_returns_empty_when_no_progress(
        self, db_session: AsyncSession, users
    ):
        repo = AnalyticsRepository(db_session)
        assert await repo.get_step_completion_histogram() == []

    async def test_groups_by_phase_and_step_count(
        self, db_session: AsyncSession, users
    ):
        progress_repo = StepProgressRepository(db_session)
        # User A: 2 steps in phase 0
        await progress_repo.create_if_not_exists(USER_A, "topic-1", "step-1", 1, 0)
        await progress_repo.create_if_not_exists(USER_A, "topic-1", "step-2", 2, 0)
        # User B: 1 step in phase 0
        await progress_repo.create_if_not_exists(USER_B, "topic-1", "step-1", 1, 0)
        # User C: 1 step in phase 1
        await progress_repo.create_if_not_exists(USER_C, "topic-2", "step-1", 1, 1)
        await db_session.flush()

        repo = AnalyticsRepository(db_session)
        histogram = await repo.get_step_completion_histogram()

        # Convert to a dict for easier assertions: (phase_id, step_count) -> num_users
        hist_map = {(pid, sc): nu for pid, sc, nu in histogram}
        assert hist_map[(0, 2)] == 1  # User A: 2 steps in phase 0
        assert hist_map[(0, 1)] == 1  # User B: 1 step in phase 0
        assert hist_map[(1, 1)] == 1  # User C: 1 step in phase 1


# =========================================================================
# get_signups_by_month
# =========================================================================


class TestGetSignupsByMonth:
    async def test_returns_empty_when_no_users(self, db_session: AsyncSession):
        repo = AnalyticsRepository(db_session)
        assert await repo.get_signups_by_month() == []

    async def test_groups_by_month(self, db_session: AsyncSession, users):
        repo = AnalyticsRepository(db_session)
        result = await repo.get_signups_by_month()

        # All 4 users were created in the same test run, so one month
        assert len(result) == 1
        month_str, count = result[0]
        assert count == 4
        # Month should be YYYY-MM format
        assert len(month_str) == 7
        assert "-" in month_str


# =========================================================================
# get_submission_stats_by_phase
# =========================================================================


class TestGetSubmissionStatsByPhase:
    async def test_returns_empty_when_no_submissions(
        self, db_session: AsyncSession, users
    ):
        repo = AnalyticsRepository(db_session)
        assert await repo.get_submission_stats_by_phase() == {}

    async def test_counts_total_and_successful(self, db_session: AsyncSession, users):
        sub_repo = SubmissionRepository(db_session)
        # Phase 0: 2 attempts, 1 successful (both verification_completed)
        await sub_repo.create(
            user_id=USER_A,
            requirement_id="github-profile",
            submission_type=SubmissionType.GITHUB_PROFILE,
            phase_id=0,
            submitted_value="https://github.com/a",
            extracted_username="a",
            is_validated=False,
            verification_completed=True,
        )
        await sub_repo.create(
            user_id=USER_B,
            requirement_id="github-profile",
            submission_type=SubmissionType.GITHUB_PROFILE,
            phase_id=0,
            submitted_value="https://github.com/b",
            extracted_username="b",
            is_validated=True,
            verification_completed=True,
        )
        await db_session.flush()

        repo = AnalyticsRepository(db_session)
        stats = await repo.get_submission_stats_by_phase()
        assert 0 in stats
        total, successful = stats[0]
        assert total == 2
        assert successful == 1

    async def test_excludes_non_completed_verifications(
        self, db_session: AsyncSession, users
    ):
        """Submissions blocked by server error are excluded."""
        sub_repo = SubmissionRepository(db_session)
        await sub_repo.create(
            user_id=USER_A,
            requirement_id="github-profile",
            submission_type=SubmissionType.GITHUB_PROFILE,
            phase_id=0,
            submitted_value="https://github.com/a",
            extracted_username="a",
            is_validated=False,
            verification_completed=False,  # Server error — should be excluded
        )
        await db_session.flush()

        repo = AnalyticsRepository(db_session)
        stats = await repo.get_submission_stats_by_phase()
        assert stats == {}


# =========================================================================
# get_activity_by_day_of_week
# =========================================================================


class TestGetActivityByDayOfWeek:
    async def test_returns_empty_when_no_progress(
        self, db_session: AsyncSession, users
    ):
        repo = AnalyticsRepository(db_session)
        assert await repo.get_activity_by_day_of_week() == {}

    async def test_aggregates_by_iso_day(self, db_session: AsyncSession, users):
        progress_repo = StepProgressRepository(db_session)
        await progress_repo.create_if_not_exists(USER_A, "topic-1", "step-1", 1, 0)
        await progress_repo.create_if_not_exists(USER_A, "topic-1", "step-2", 2, 0)
        await db_session.flush()

        repo = AnalyticsRepository(db_session)
        result = await repo.get_activity_by_day_of_week()

        # Both steps created in same test run, so same day
        total = sum(result.values())
        assert total == 2
        # All days should be valid ISO day numbers (1-7)
        for day in result:
            assert 1 <= day <= 7


# =========================================================================
# get_provider_distribution
# =========================================================================


class TestGetProviderDistribution:
    async def test_returns_empty_when_no_submissions(
        self, db_session: AsyncSession, users
    ):
        repo = AnalyticsRepository(db_session)
        assert await repo.get_provider_distribution() == []

    async def test_counts_validated_submissions_by_provider(
        self, db_session: AsyncSession, users
    ):
        sub_repo = SubmissionRepository(db_session)
        await sub_repo.create(
            user_id=USER_A,
            requirement_id="deploy-1",
            submission_type=SubmissionType.DEPLOYED_API,
            phase_id=4,
            submitted_value="https://app.azure.com",
            extracted_username=None,
            is_validated=True,
            cloud_provider="azure",
        )
        await sub_repo.create(
            user_id=USER_B,
            requirement_id="deploy-1",
            submission_type=SubmissionType.DEPLOYED_API,
            phase_id=4,
            submitted_value="https://app.aws.com",
            extracted_username=None,
            is_validated=True,
            cloud_provider="aws",
        )
        await sub_repo.create(
            user_id=USER_C,
            requirement_id="deploy-1",
            submission_type=SubmissionType.DEPLOYED_API,
            phase_id=4,
            submitted_value="https://app2.azure.com",
            extracted_username=None,
            is_validated=True,
            cloud_provider="azure",
        )
        await db_session.flush()

        repo = AnalyticsRepository(db_session)
        result = await repo.get_provider_distribution()

        provider_map = {provider: count for provider, count in result}
        assert provider_map["azure"] == 2
        assert provider_map["aws"] == 1

    async def test_excludes_unvalidated_submissions(
        self, db_session: AsyncSession, users
    ):
        sub_repo = SubmissionRepository(db_session)
        await sub_repo.create(
            user_id=USER_A,
            requirement_id="deploy-1",
            submission_type=SubmissionType.DEPLOYED_API,
            phase_id=4,
            submitted_value="https://app.gcp.com",
            extracted_username=None,
            is_validated=False,
            cloud_provider="gcp",
        )
        await db_session.flush()

        repo = AnalyticsRepository(db_session)
        assert await repo.get_provider_distribution() == []

    async def test_excludes_submissions_without_provider(
        self, db_session: AsyncSession, users
    ):
        sub_repo = SubmissionRepository(db_session)
        await sub_repo.create(
            user_id=USER_A,
            requirement_id="github-profile",
            submission_type=SubmissionType.GITHUB_PROFILE,
            phase_id=0,
            submitted_value="https://github.com/a",
            extracted_username="a",
            is_validated=True,
            cloud_provider=None,
        )
        await db_session.flush()

        repo = AnalyticsRepository(db_session)
        assert await repo.get_provider_distribution() == []


# =========================================================================
# Snapshot (upsert + read)
# =========================================================================


class TestSnapshot:
    async def test_returns_none_when_no_snapshot(self, db_session: AsyncSession):
        repo = AnalyticsRepository(db_session)
        assert await repo.get_snapshot_data() is None

    async def test_upsert_creates_snapshot(self, db_session: AsyncSession):
        repo = AnalyticsRepository(db_session)
        now = datetime.now(UTC)
        await repo.upsert_snapshot('{"total_users": 10}', now)
        await db_session.flush()

        data = await repo.get_snapshot_data()
        assert data == '{"total_users": 10}'

    async def test_upsert_overwrites_existing(self, db_session: AsyncSession):
        repo = AnalyticsRepository(db_session)
        now = datetime.now(UTC)
        await repo.upsert_snapshot('{"total_users": 10}', now)
        await db_session.flush()

        later = datetime.now(UTC)
        await repo.upsert_snapshot('{"total_users": 20}', later)
        await db_session.flush()

        data = await repo.get_snapshot_data()
        assert data == '{"total_users": 20}'


# =========================================================================
# get_program_completers
# =========================================================================


class TestGetProgramCompleters:
    async def test_returns_zero_when_empty_requirements(
        self, db_session: AsyncSession, users
    ):
        repo = AnalyticsRepository(db_session)
        assert await repo.get_program_completers({}) == 0

    async def test_returns_zero_when_no_progress(self, db_session: AsyncSession, users):
        repo = AnalyticsRepository(db_session)
        assert await repo.get_program_completers({0: (2, 1)}) == 0

    async def test_counts_user_completing_single_phase_steps_only(
        self, db_session: AsyncSession, users
    ):
        """User completed enough steps in a phase with no hands-on."""
        progress_repo = StepProgressRepository(db_session)
        await progress_repo.create_if_not_exists(USER_A, "topic-1", "step-1", 1, 0)
        await progress_repo.create_if_not_exists(USER_A, "topic-1", "step-2", 2, 0)
        await db_session.flush()

        repo = AnalyticsRepository(db_session)
        assert await repo.get_program_completers({0: (2, 0)}) == 1

    async def test_excludes_user_with_insufficient_steps(
        self, db_session: AsyncSession, users
    ):
        progress_repo = StepProgressRepository(db_session)
        await progress_repo.create_if_not_exists(USER_A, "topic-1", "step-1", 1, 0)
        await db_session.flush()

        repo = AnalyticsRepository(db_session)
        assert await repo.get_program_completers({0: (3, 0)}) == 0

    async def test_counts_user_completing_steps_and_hands_on(
        self, db_session: AsyncSession, users
    ):
        """User completed both steps AND hands-on for a single phase."""
        progress_repo = StepProgressRepository(db_session)
        sub_repo = SubmissionRepository(db_session)

        await progress_repo.create_if_not_exists(USER_A, "topic-1", "step-1", 1, 0)
        await sub_repo.create(
            user_id=USER_A,
            requirement_id="github-profile",
            submission_type=SubmissionType.GITHUB_PROFILE,
            phase_id=0,
            submitted_value="https://github.com/a",
            extracted_username="a",
            is_validated=True,
        )
        await db_session.flush()

        repo = AnalyticsRepository(db_session)
        assert await repo.get_program_completers({0: (1, 1)}) == 1

    async def test_excludes_user_missing_hands_on(
        self, db_session: AsyncSession, users
    ):
        """User completed steps but NOT hands-on."""
        progress_repo = StepProgressRepository(db_session)
        await progress_repo.create_if_not_exists(USER_A, "topic-1", "step-1", 1, 0)
        await db_session.flush()

        repo = AnalyticsRepository(db_session)
        assert await repo.get_program_completers({0: (1, 1)}) == 0

    async def test_excludes_user_with_unvalidated_hands_on(
        self, db_session: AsyncSession, users
    ):
        """Unvalidated submissions don't count toward hands-on."""
        progress_repo = StepProgressRepository(db_session)
        sub_repo = SubmissionRepository(db_session)

        await progress_repo.create_if_not_exists(USER_A, "topic-1", "step-1", 1, 0)
        await sub_repo.create(
            user_id=USER_A,
            requirement_id="github-profile",
            submission_type=SubmissionType.GITHUB_PROFILE,
            phase_id=0,
            submitted_value="https://github.com/a",
            extracted_username="a",
            is_validated=False,
        )
        await db_session.flush()

        repo = AnalyticsRepository(db_session)
        assert await repo.get_program_completers({0: (1, 1)}) == 0

    async def test_requires_all_phases_completed(self, db_session: AsyncSession, users):
        """User must complete ALL phases, not just one."""
        progress_repo = StepProgressRepository(db_session)
        sub_repo = SubmissionRepository(db_session)

        # User A completes phase 0 fully
        await progress_repo.create_if_not_exists(USER_A, "topic-1", "step-1", 1, 0)
        await sub_repo.create(
            user_id=USER_A,
            requirement_id="github-profile",
            submission_type=SubmissionType.GITHUB_PROFILE,
            phase_id=0,
            submitted_value="https://github.com/a",
            extracted_username="a",
            is_validated=True,
        )
        # User A has NO progress in phase 1
        await db_session.flush()

        repo = AnalyticsRepository(db_session)
        result = await repo.get_program_completers({0: (1, 1), 1: (1, 0)})
        assert result == 0

    async def test_counts_user_completing_multiple_phases(
        self, db_session: AsyncSession, users
    ):
        """User completed both phases — should be counted."""
        progress_repo = StepProgressRepository(db_session)
        sub_repo = SubmissionRepository(db_session)

        # Phase 0: steps + hands-on
        await progress_repo.create_if_not_exists(USER_A, "topic-1", "step-1", 1, 0)
        await sub_repo.create(
            user_id=USER_A,
            requirement_id="github-profile",
            submission_type=SubmissionType.GITHUB_PROFILE,
            phase_id=0,
            submitted_value="https://github.com/a",
            extracted_username="a",
            is_validated=True,
        )
        # Phase 1: steps only
        await progress_repo.create_if_not_exists(USER_A, "topic-2", "step-1", 1, 1)
        await db_session.flush()

        repo = AnalyticsRepository(db_session)
        result = await repo.get_program_completers({0: (1, 1), 1: (1, 0)})
        assert result == 1

    async def test_multiple_users_mixed_completion(
        self, db_session: AsyncSession, users
    ):
        """Two users: one completes everything, one doesn't."""
        progress_repo = StepProgressRepository(db_session)
        sub_repo = SubmissionRepository(db_session)

        # User A: completes both phases
        await progress_repo.create_if_not_exists(USER_A, "topic-1", "step-1", 1, 0)
        await sub_repo.create(
            user_id=USER_A,
            requirement_id="github-profile",
            submission_type=SubmissionType.GITHUB_PROFILE,
            phase_id=0,
            submitted_value="https://github.com/a",
            extracted_username="a",
            is_validated=True,
        )
        await progress_repo.create_if_not_exists(USER_A, "topic-2", "step-1", 1, 1)

        # User B: completes phase 0 only
        await progress_repo.create_if_not_exists(USER_B, "topic-1", "step-1", 1, 0)
        await sub_repo.create(
            user_id=USER_B,
            requirement_id="github-profile",
            submission_type=SubmissionType.GITHUB_PROFILE,
            phase_id=0,
            submitted_value="https://github.com/b",
            extracted_username="b",
            is_validated=True,
        )
        await db_session.flush()

        repo = AnalyticsRepository(db_session)
        result = await repo.get_program_completers({0: (1, 1), 1: (1, 0)})
        assert result == 1  # Only User A
