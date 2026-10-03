"""Unit tests for page-route contracts not covered by real-render smoke tests."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from learn_to_cloud.models import User
from learn_to_cloud.routes.pages_routes import (
    community_page,
    phase_page,
    stats_page_redirect,
    topic_page,
)


@pytest.fixture(autouse=True)
def _patch_templates():
    """Patch the templates module import for all page route tests."""
    mock_templates = MagicMock()
    with patch("learn_to_cloud.routes.pages_routes.templates", mock_templates):
        yield mock_templates


def _mock_request(mock_templates: MagicMock) -> tuple[MagicMock, MagicMock]:
    """Build mock Request. Returns (request, template_response_mock)."""
    request = MagicMock()
    mock_templates.TemplateResponse.reset_mock()
    return request, mock_templates.TemplateResponse


def _fake_phase(*, order: int = 1, name: str = "Phase 1", slug: str = "phase1"):
    """Build a minimal mock phase object."""
    phase = MagicMock()
    phase.order = order
    phase.name = name
    phase.slug = slug
    phase.topics = []
    phase.hands_on_verification = None
    return phase


@pytest.mark.unit
class TestPhasePage:
    """Tests for GET /phase/{phase_id}."""

    async def test_phase_returns_404_for_unknown_phase(self, _patch_templates):
        """Non-existent phase renders 404 template."""
        request, template = _mock_request(_patch_templates)
        mock_db = AsyncMock()

        with (
            patch(
                "learn_to_cloud.routes.pages_routes.get_phase_by_slug",
                return_value=None,
            ),
        ):
            await phase_page(
                request,
                phase_id=999,
                db=mock_db,
                account=User(id=1, github_username="testuser"),
            )

        assert template.call_args[0][1] == "pages/404.html"
        # Verify 404 status code is set
        call_kwargs = template.call_args[1] if template.call_args[1] else {}
        assert call_kwargs.get("status_code") == 404


@pytest.mark.unit
class TestTopicPage:
    """Tests for GET /phase/{phase_id}/{topic_slug}."""

    async def test_topic_returns_404_when_topic_missing(self, _patch_templates):
        """Existing phase but missing topic renders 404."""
        request, template = _mock_request(_patch_templates)
        mock_db = AsyncMock()
        phase = _fake_phase()
        phase.topics = []  # no topic matches the requested slug

        with (
            patch(
                "learn_to_cloud.routes.pages_routes.get_phase_by_slug",
                return_value=phase,
            ),
        ):
            await topic_page(
                request,
                phase_id=1,
                topic_slug="bad-topic",
                db=mock_db,
                account=User(id=1, github_username="testuser"),
            )

        assert template.call_args[0][1] == "pages/404.html"


@pytest.mark.unit
class TestCommunityPage:
    """Tests for the public community routes."""

    async def test_community_renders_with_community_context(self, _patch_templates):
        request, template = _mock_request(_patch_templates)
        mock_db = AsyncMock()
        mock_community = MagicMock()

        with (
            patch(
                "learn_to_cloud.routes.pages_routes.get_community_page_data",
                autospec=True,
                return_value=mock_community,
            ),
        ):
            await community_page(request, mock_db, account=None)

        assert template.call_args[0][1] == "pages/community.html"
        ctx = template.call_args[0][2]
        assert ctx["community"] is mock_community
        assert len(ctx["community_links"]) == 5
        assert ctx["user"] is None

    async def test_stats_redirects_permanently_to_community(self):
        response = await stats_page_redirect()

        assert response.status_code == 308
        assert response.headers["location"] == "/community"
