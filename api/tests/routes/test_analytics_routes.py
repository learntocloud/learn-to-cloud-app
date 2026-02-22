"""Unit tests for analytics routes.

Tests cover:
- GET /status — public status page with health + analytics data

Testing approach:
- Call the handler directly with mocked dependencies
- Mock template rendering to verify the context dict
- Verify correct analytics fallback on service errors
"""

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from routes.analytics_routes import status_page
from schemas import CommunityAnalytics


def _mock_request() -> tuple[MagicMock, MagicMock]:
    """Build a mock Request and a mock for the templates module.

    Returns (request, template_response_mock).
    """
    request = MagicMock()
    request.app.state.engine = MagicMock()

    template_response = MagicMock()
    return request, template_response


def _make_analytics(**overrides) -> CommunityAnalytics:
    """Build a CommunityAnalytics with sensible defaults."""
    defaults = {
        "total_users": 100,
        "active_learners_30d": 42,
        "completion_rate": 0.15,
        "phase_distribution": [],
        "signup_trends": [],
        "verification_stats": [],
        "activity_by_day": [],
        "generated_at": datetime(2024, 6, 1, tzinfo=UTC),
    }
    defaults.update(overrides)
    return CommunityAnalytics(**defaults)


@pytest.mark.unit
class TestStatusPage:
    """Tests for GET /status."""

    @pytest.fixture(autouse=True)
    def _patch_templates(self):
        """Patch the templates module import so we can inspect calls."""
        self.template_response = MagicMock()
        mock_templates = MagicMock()
        mock_templates.TemplateResponse = self.template_response
        with patch("routes.analytics_routes.templates", mock_templates):
            yield

    async def test_status_page_renders_for_anonymous_user(self):
        """Anonymous users (user_id=None) can view the status page."""
        request = MagicMock()
        request.app.state.engine = MagicMock()
        mock_db = AsyncMock()
        analytics = _make_analytics()

        with patch(
            "routes.analytics_routes.comprehensive_health_check",
            autospec=True,
            return_value={"database": True, "azure_auth": None, "pool": None},
        ), patch(
            "routes.analytics_routes.get_community_analytics",
            autospec=True,
            return_value=analytics,
        ):
            await status_page(request, mock_db, user_id=None)

        # Verify template was called with correct template name
        self.template_response.assert_called_once()
        call_args = self.template_response.call_args
        assert call_args[0][0] == "pages/status.html"

        # Verify context
        ctx = call_args[0][1]
        assert ctx["user"] is None
        assert ctx["overall_status"] == "operational"
        assert ctx["analytics"] == analytics

    async def test_status_page_renders_for_authenticated_user(self):
        """Authenticated users see their user object in context."""
        request = MagicMock()
        request.app.state.engine = MagicMock()
        mock_db = AsyncMock()
        analytics = _make_analytics()
        mock_user = MagicMock()
        mock_user.id = 42

        with patch(
            "routes.analytics_routes.comprehensive_health_check",
            autospec=True,
            return_value={"database": True, "azure_auth": None, "pool": None},
        ), patch(
            "routes.analytics_routes.get_community_analytics",
            autospec=True,
            return_value=analytics,
        ), patch(
            "routes.analytics_routes.get_user_by_id",
            autospec=True,
            return_value=mock_user,
        ):
            await status_page(request, mock_db, user_id=42)

        ctx = self.template_response.call_args[0][1]
        assert ctx["user"] is mock_user

    async def test_status_page_shows_down_when_db_unhealthy(self):
        """overall_status is 'down' when database health check fails."""
        request = MagicMock()
        request.app.state.engine = MagicMock()
        mock_db = AsyncMock()
        analytics = _make_analytics()

        with patch(
            "routes.analytics_routes.comprehensive_health_check",
            autospec=True,
            return_value={"database": False, "azure_auth": None, "pool": None},
        ), patch(
            "routes.analytics_routes.get_community_analytics",
            autospec=True,
            return_value=analytics,
        ):
            await status_page(request, mock_db, user_id=None)

        ctx = self.template_response.call_args[0][1]
        assert ctx["overall_status"] == "down"

    async def test_status_page_shows_down_when_azure_auth_fails(self):
        """overall_status is 'down' when Azure auth health check is False."""
        request = MagicMock()
        request.app.state.engine = MagicMock()
        mock_db = AsyncMock()
        analytics = _make_analytics()

        with patch(
            "routes.analytics_routes.comprehensive_health_check",
            autospec=True,
            return_value={"database": True, "azure_auth": False, "pool": None},
        ), patch(
            "routes.analytics_routes.get_community_analytics",
            autospec=True,
            return_value=analytics,
        ):
            await status_page(request, mock_db, user_id=None)

        ctx = self.template_response.call_args[0][1]
        assert ctx["overall_status"] == "down"

    async def test_status_page_operational_when_azure_auth_is_none(self):
        """overall_status is 'operational' when Azure auth is None (not used)."""
        request = MagicMock()
        request.app.state.engine = MagicMock()
        mock_db = AsyncMock()
        analytics = _make_analytics()

        with patch(
            "routes.analytics_routes.comprehensive_health_check",
            autospec=True,
            return_value={"database": True, "azure_auth": None, "pool": None},
        ), patch(
            "routes.analytics_routes.get_community_analytics",
            autospec=True,
            return_value=analytics,
        ):
            await status_page(request, mock_db, user_id=None)

        ctx = self.template_response.call_args[0][1]
        assert ctx["overall_status"] == "operational"

    async def test_status_page_falls_back_on_analytics_error(self):
        """When analytics service raises, page renders with zeroed analytics."""
        request = MagicMock()
        request.app.state.engine = MagicMock()
        mock_db = AsyncMock()

        with patch(
            "routes.analytics_routes.comprehensive_health_check",
            autospec=True,
            return_value={"database": True, "azure_auth": None, "pool": None},
        ), patch(
            "routes.analytics_routes.get_community_analytics",
            autospec=True,
            side_effect=RuntimeError("DB exploded"),
        ):
            await status_page(request, mock_db, user_id=None)

        ctx = self.template_response.call_args[0][1]
        # Should get a fallback CommunityAnalytics with zeros
        assert ctx["analytics"].total_users == 0
        assert ctx["analytics"].active_learners_30d == 0
        assert ctx["analytics"].completion_rate == 0.0
        # Status should still reflect health check, not analytics
        assert ctx["overall_status"] == "operational"
