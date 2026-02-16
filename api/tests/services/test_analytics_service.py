"""Unit tests for analytics_service.

Tests cover:
- _build_cumulative_trends produces correct cumulative sums
- _compute_users_completed_steps filters histogram correctly
- get_community_analytics returns cached / snapshot / empty fallback
- _empty_analytics returns zeroed-out payload
"""

from unittest.mock import AsyncMock, patch

import pytest

from services.analytics_service import (
    _build_cumulative_trends,
    _compute_users_completed_steps,
    _empty_analytics,
    _local_cache,
    get_community_analytics,
)


@pytest.fixture(autouse=True)
def _clear_cache():
    """Clear the in-memory analytics cache before each test."""
    _local_cache.clear()
    yield
    _local_cache.clear()


# =========================================================================
# _build_cumulative_trends
# =========================================================================


@pytest.mark.unit
class TestBuildCumulativeTrends:
    def test_empty_input(self):
        assert _build_cumulative_trends([]) == []

    def test_single_month(self):
        trends = _build_cumulative_trends([("2026-01", 10)])
        assert len(trends) == 1
        assert trends[0].month == "2026-01"
        assert trends[0].count == 10
        assert trends[0].cumulative == 10

    def test_accumulates_across_months(self):
        trends = _build_cumulative_trends(
            [
                ("2026-01", 5),
                ("2026-02", 15),
                ("2026-03", 10),
            ]
        )
        assert trends[0].cumulative == 5
        assert trends[1].cumulative == 20
        assert trends[2].cumulative == 30

    def test_handles_zero_counts(self):
        trends = _build_cumulative_trends(
            [
                ("2026-01", 10),
                ("2026-02", 0),
                ("2026-03", 5),
            ]
        )
        assert trends[1].cumulative == 10  # No change
        assert trends[2].cumulative == 15


# =========================================================================
# _compute_users_completed_steps
# =========================================================================


@pytest.mark.unit
class TestComputeUsersCompletedSteps:
    def test_empty_histogram(self):
        assert _compute_users_completed_steps([], phase_id=0, required_steps=3) == 0

    def test_counts_users_meeting_threshold(self):
        histogram = [
            (0, 1, 10),  # 10 users with 1 step in phase 0
            (0, 2, 5),  # 5 users with 2 steps in phase 0
            (0, 3, 3),  # 3 users with 3 steps in phase 0
            (0, 5, 2),  # 2 users with 5 steps in phase 0
        ]
        # Required: 3 steps → users with 3 or more = 3 + 2 = 5
        assert (
            _compute_users_completed_steps(histogram, phase_id=0, required_steps=3) == 5
        )

    def test_filters_by_phase_id(self):
        histogram = [
            (0, 3, 10),  # phase 0
            (1, 3, 7),  # phase 1
        ]
        assert (
            _compute_users_completed_steps(histogram, phase_id=1, required_steps=3) == 7
        )

    def test_zero_required_steps_counts_all(self):
        histogram = [
            (0, 1, 10),
            (0, 5, 5),
        ]
        # required_steps=0 means all users meet the threshold
        assert (
            _compute_users_completed_steps(histogram, phase_id=0, required_steps=0)
            == 15
        )

    def test_no_users_meet_threshold(self):
        histogram = [
            (0, 1, 10),
            (0, 2, 5),
        ]
        assert (
            _compute_users_completed_steps(histogram, phase_id=0, required_steps=5) == 0
        )


# =========================================================================
# _empty_analytics
# =========================================================================


@pytest.mark.unit
class TestEmptyAnalytics:
    def test_returns_zeroed_payload(self):
        result = _empty_analytics()
        assert result.total_users == 0
        assert result.active_learners_30d == 0
        assert result.completion_rate == 0.0
        assert result.phase_distribution == []
        assert result.signup_trends == []
        assert result.verification_stats == []
        assert result.activity_by_day == []
        assert result.generated_at is not None


# =========================================================================
# get_community_analytics
# =========================================================================


@pytest.mark.unit
class TestGetCommunityAnalytics:
    @pytest.mark.asyncio
    async def test_returns_cached_value_when_available(self):
        """In-memory cache hit bypasses DB entirely."""
        cached = _empty_analytics()
        _local_cache["analytics"] = cached

        result = await get_community_analytics(db=None)
        assert result is cached

    @pytest.mark.asyncio
    async def test_returns_snapshot_from_db(self):
        """When no cache, reads from DB snapshot."""
        analytics = _empty_analytics()
        snapshot_json = analytics.model_dump_json()

        mock_db = AsyncMock()
        with patch(
            "services.analytics_service.AnalyticsRepository", autospec=True
        ) as mock_repo_class:
            mock_repo = mock_repo_class.return_value
            mock_repo.get_snapshot_data = AsyncMock(return_value=snapshot_json)

            result = await get_community_analytics(db=mock_db)

            assert result.total_users == 0
            mock_repo.get_snapshot_data.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_caches_snapshot_after_db_read(self):
        """After reading from DB, result is stored in local cache."""
        analytics = _empty_analytics()
        snapshot_json = analytics.model_dump_json()

        mock_db = AsyncMock()
        with patch(
            "services.analytics_service.AnalyticsRepository", autospec=True
        ) as mock_repo_class:
            mock_repo = mock_repo_class.return_value
            mock_repo.get_snapshot_data = AsyncMock(return_value=snapshot_json)

            await get_community_analytics(db=mock_db)
            assert "analytics" in _local_cache

    @pytest.mark.asyncio
    async def test_returns_empty_when_no_cache_no_db(self):
        """With no cache and no DB session, returns zeroed-out placeholder."""
        result = await get_community_analytics(db=None)
        assert result.total_users == 0

    @pytest.mark.asyncio
    async def test_returns_empty_when_no_snapshot_in_db(self):
        """DB session provided but no snapshot row exists yet."""
        mock_db = AsyncMock()
        with patch(
            "services.analytics_service.AnalyticsRepository", autospec=True
        ) as mock_repo_class:
            mock_repo = mock_repo_class.return_value
            mock_repo.get_snapshot_data = AsyncMock(return_value=None)

            result = await get_community_analytics(db=mock_db)
            assert result.total_users == 0
