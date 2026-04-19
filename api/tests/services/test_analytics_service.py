"""Unit tests for analytics_service.

Tests cover:
- get_community_analytics returns correct CommunityAnalytics from repo queries
"""

from unittest.mock import AsyncMock, patch

import pytest

from services.analytics_service import get_community_analytics


@pytest.mark.unit
class TestGetCommunityAnalytics:
    @pytest.mark.asyncio
    async def test_returns_analytics_from_repo(self):
        """Queries repo for total_users and active_learners_30d."""
        mock_db = AsyncMock()
        with patch(
            "services.analytics_service.AnalyticsRepository", autospec=True
        ) as mock_repo_class:
            mock_repo = mock_repo_class.return_value
            mock_repo.get_total_users = AsyncMock(return_value=100)
            mock_repo.get_active_learners = AsyncMock(return_value=42)

            result = await get_community_analytics(db=mock_db)

            assert result.total_users == 100
            assert result.active_learners_30d == 42
            assert result.generated_at is not None
            mock_repo.get_total_users.assert_awaited_once()
            mock_repo.get_active_learners.assert_awaited_once_with(days=30)

    @pytest.mark.asyncio
    async def test_returns_zero_when_no_data(self):
        """Returns zeros when repo returns zeros."""
        mock_db = AsyncMock()
        with patch(
            "services.analytics_service.AnalyticsRepository", autospec=True
        ) as mock_repo_class:
            mock_repo = mock_repo_class.return_value
            mock_repo.get_total_users = AsyncMock(return_value=0)
            mock_repo.get_active_learners = AsyncMock(return_value=0)

            result = await get_community_analytics(db=mock_db)

            assert result.total_users == 0
            assert result.active_learners_30d == 0
