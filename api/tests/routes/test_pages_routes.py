"""Unit tests for pages routes.

Tests cover:
- GET / — home page (public)
- GET /curriculum — curriculum page (public)
- GET /phase/{id} — phase detail (requires auth)
- GET /phase/{id}/{topic} — topic detail (requires auth)
- GET /dashboard — user dashboard (requires auth)
- GET /account — account settings (requires auth)
- GET /faq — FAQ page (public)
- GET /privacy — privacy page (public)
- GET /terms — terms page (public)

Testing approach:
- Call handler functions directly with mocked dependencies
- Verify template name and context dict passed to TemplateResponse
- No real template rendering (that's Jinja2's responsibility, not ours)
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from routes.pages_routes import (
    account_page,
    curriculum_page,
    dashboard_page,
    faq_page,
    home_page,
    phase_page,
    privacy_page,
    terms_page,
    topic_page,
)


@pytest.fixture(autouse=True)
def _patch_templates():
    """Patch the templates module import for all page route tests."""
    mock_templates = MagicMock()
    with patch("routes.pages_routes.templates", mock_templates):
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


def _fake_topic(*, topic_id: str = "topic-1", slug: str = "linux-basics"):
    """Build a minimal mock topic object."""
    topic = MagicMock()
    topic.id = topic_id
    topic.slug = slug
    topic.learning_steps = []
    return topic


@pytest.mark.unit
class TestHomePage:
    """Tests for GET /."""

    async def test_home_renders_for_anonymous_user(self, _patch_templates):
        """Anonymous users see the home page with phases."""
        request, template = _mock_request(_patch_templates)
        mock_db = AsyncMock()
        phases = [_fake_phase(order=i) for i in range(1, 6)]

        with (
            patch("routes.pages_routes.get_all_phases", return_value=phases),
            patch(
                "routes.pages_routes.get_user_by_id",
                autospec=True,
                return_value=None,
            ),
        ):
            await home_page(request, mock_db, user_id=None)

        template.assert_called_once()
        ctx = template.call_args[0][1]
        assert ctx["request"] is request
        assert ctx["user"] is None
        assert ctx["phases"] == phases
        assert template.call_args[0][0] == "pages/home.html"

    async def test_home_renders_for_authenticated_user(self, _patch_templates):
        """Authenticated users see their user object in context."""
        request, template = _mock_request(_patch_templates)
        mock_db = AsyncMock()
        mock_user = MagicMock()
        phases = [_fake_phase()]

        with (
            patch("routes.pages_routes.get_all_phases", return_value=phases),
            patch(
                "routes.pages_routes.get_user_by_id",
                autospec=True,
                return_value=mock_user,
            ),
        ):
            await home_page(request, mock_db, user_id=42)

        ctx = template.call_args[0][1]
        assert ctx["user"] is mock_user


@pytest.mark.unit
class TestCurriculumPage:
    """Tests for GET /curriculum."""

    async def test_curriculum_renders_with_phases(self, _patch_templates):
        """Curriculum page passes all phases to template."""
        request, template = _mock_request(_patch_templates)
        mock_db = AsyncMock()
        phases = [_fake_phase(order=i) for i in range(1, 6)]

        with (
            patch("routes.pages_routes.get_all_phases", return_value=phases),
            patch(
                "routes.pages_routes.get_user_by_id",
                autospec=True,
                return_value=None,
            ),
        ):
            await curriculum_page(request, mock_db, user_id=None)

        assert template.call_args[0][0] == "pages/curriculum.html"
        ctx = template.call_args[0][1]
        assert ctx["phases"] == phases


@pytest.mark.unit
class TestPhasePage:
    """Tests for GET /phase/{phase_id}."""

    async def test_phase_returns_404_for_unknown_phase(self, _patch_templates):
        """Non-existent phase renders 404 template."""
        request, template = _mock_request(_patch_templates)
        mock_db = AsyncMock()

        with (
            patch("routes.pages_routes.get_phase_by_slug", return_value=None),
            patch(
                "routes.pages_routes.get_user_by_id",
                autospec=True,
                return_value=None,
            ),
        ):
            await phase_page(request, phase_id=999, db=mock_db, user_id=1)

        assert template.call_args[0][0] == "pages/404.html"
        # Verify 404 status code is set
        call_kwargs = template.call_args[1] if template.call_args[1] else {}
        assert call_kwargs.get("status_code") == 404

    async def test_phase_renders_with_progress_data(self, _patch_templates):
        """Valid phase renders with topics, progress, and submissions."""
        request, template = _mock_request(_patch_templates)
        mock_db = AsyncMock()
        phase = _fake_phase()
        mock_user = MagicMock()

        mock_sub_context = MagicMock()
        mock_sub_context.submissions_by_req = {}
        mock_sub_context.feedback_by_req = {}

        with (
            patch("routes.pages_routes.get_phase_by_slug", return_value=phase),
            patch(
                "routes.pages_routes.get_user_by_id",
                autospec=True,
                return_value=mock_user,
            ),
            patch(
                "routes.pages_routes.get_phase_detail_progress",
                autospec=True,
                return_value={},
            ),
            patch("routes.pages_routes.build_phase_topics", return_value=([], {})),
            patch(
                "routes.pages_routes.get_phase_submission_context",
                autospec=True,
                return_value=mock_sub_context,
            ),
            patch(
                "routes.pages_routes.is_phase_verification_locked",
                autospec=True,
                return_value=(False, None),
            ),
        ):
            await phase_page(request, phase_id=1, db=mock_db, user_id=42)

        assert template.call_args[0][0] == "pages/phase.html"
        ctx = template.call_args[0][1]
        assert ctx["phase"] is phase
        assert ctx["user"] is mock_user
        assert ctx["verification_locked"] is False


@pytest.mark.unit
class TestTopicPage:
    """Tests for GET /phase/{phase_id}/{topic_slug}."""

    async def test_topic_returns_404_when_phase_missing(self, _patch_templates):
        """Missing phase renders 404."""
        request, template = _mock_request(_patch_templates)
        mock_db = AsyncMock()

        with (
            patch("routes.pages_routes.get_phase_by_slug", return_value=None),
            patch("routes.pages_routes.get_topic_by_slugs", return_value=None),
            patch(
                "routes.pages_routes.get_user_by_id", autospec=True, return_value=None
            ),
        ):
            await topic_page(
                request, phase_id=1, topic_slug="bad-topic", db=mock_db, user_id=1
            )

        assert template.call_args[0][0] == "pages/404.html"

    async def test_topic_returns_404_when_topic_missing(self, _patch_templates):
        """Existing phase but missing topic renders 404."""
        request, template = _mock_request(_patch_templates)
        mock_db = AsyncMock()
        phase = _fake_phase()

        with (
            patch("routes.pages_routes.get_phase_by_slug", return_value=phase),
            patch("routes.pages_routes.get_topic_by_slugs", return_value=None),
            patch(
                "routes.pages_routes.get_user_by_id", autospec=True, return_value=None
            ),
        ):
            await topic_page(
                request, phase_id=1, topic_slug="bad-topic", db=mock_db, user_id=1
            )

        assert template.call_args[0][0] == "pages/404.html"

    async def test_topic_renders_with_step_data(self, _patch_templates):
        """Valid topic renders with steps and progress."""
        request, template = _mock_request(_patch_templates)
        mock_db = AsyncMock()
        phase = _fake_phase()
        topic = _fake_topic()
        phase.topics = [topic]

        with (
            patch("routes.pages_routes.get_phase_by_slug", return_value=phase),
            patch("routes.pages_routes.get_topic_by_slugs", return_value=topic),
            patch(
                "routes.pages_routes.get_user_by_id",
                autospec=True,
                return_value=MagicMock(),
            ),
            patch(
                "routes.pages_routes.get_valid_completed_steps",
                autospec=True,
                return_value=[],
            ),
            patch("routes.pages_routes.build_topic_nav", return_value=(None, None)),
        ):
            await topic_page(
                request, phase_id=1, topic_slug="linux-basics", db=mock_db, user_id=1
            )

        assert template.call_args[0][0] == "pages/topic.html"
        ctx = template.call_args[0][1]
        assert ctx["topic"] is topic


@pytest.mark.unit
class TestDashboardPage:
    """Tests for GET /dashboard."""

    async def test_dashboard_renders_for_authenticated_user(self, _patch_templates):
        """Dashboard renders with user and dashboard data."""
        request, template = _mock_request(_patch_templates)
        mock_db = AsyncMock()
        mock_user = MagicMock()
        mock_dashboard = MagicMock()

        with (
            patch(
                "routes.pages_routes.get_user_by_id",
                autospec=True,
                return_value=mock_user,
            ),
            patch(
                "routes.pages_routes.get_dashboard_data",
                autospec=True,
                return_value=mock_dashboard,
            ),
        ):
            await dashboard_page(request, mock_db, user_id=42)

        assert template.call_args[0][0] == "pages/dashboard.html"
        ctx = template.call_args[0][1]
        assert ctx["user"] is mock_user
        assert ctx["dashboard"] is mock_dashboard

    async def test_dashboard_returns_404_when_user_not_found(self, _patch_templates):
        """Dashboard returns 404 if user_id doesn't match a DB user."""
        request, template = _mock_request(_patch_templates)
        mock_db = AsyncMock()

        with patch(
            "routes.pages_routes.get_user_by_id", autospec=True, return_value=None
        ):
            await dashboard_page(request, mock_db, user_id=999)

        assert template.call_args[0][0] == "pages/404.html"
        call_kwargs = template.call_args[1] if template.call_args[1] else {}
        assert call_kwargs.get("status_code") == 404


@pytest.mark.unit
class TestAccountPage:
    """Tests for GET /account."""

    async def test_account_renders_for_user(self, _patch_templates):
        """Account page renders with user context."""
        request, template = _mock_request(_patch_templates)
        mock_db = AsyncMock()
        mock_user = MagicMock()

        with patch(
            "routes.pages_routes.get_user_by_id", autospec=True, return_value=mock_user
        ):
            await account_page(request, mock_db, user_id=42)

        assert template.call_args[0][0] == "pages/account.html"
        ctx = template.call_args[0][1]
        assert ctx["user"] is mock_user

    async def test_account_returns_404_when_user_not_found(self, _patch_templates):
        """Account returns 404 if user doesn't exist."""
        request, template = _mock_request(_patch_templates)
        mock_db = AsyncMock()

        with patch(
            "routes.pages_routes.get_user_by_id", autospec=True, return_value=None
        ):
            await account_page(request, mock_db, user_id=999)

        assert template.call_args[0][0] == "pages/404.html"


@pytest.mark.unit
class TestPublicPages:
    """Tests for public pages: /faq, /privacy, /terms."""

    async def test_faq_page_renders(self, _patch_templates):
        """FAQ page renders with FAQs in context."""
        request, template = _mock_request(_patch_templates)
        mock_db = AsyncMock()

        with patch(
            "routes.pages_routes.get_user_by_id", autospec=True, return_value=None
        ):
            await faq_page(request, mock_db, user_id=None)

        assert template.call_args[0][0] == "pages/faq.html"
        ctx = template.call_args[0][1]
        assert "faqs" in ctx

    async def test_privacy_page_renders(self, _patch_templates):
        """Privacy page renders successfully."""
        request, template = _mock_request(_patch_templates)
        mock_db = AsyncMock()

        with patch(
            "routes.pages_routes.get_user_by_id", autospec=True, return_value=None
        ):
            await privacy_page(request, mock_db, user_id=None)

        assert template.call_args[0][0] == "pages/privacy.html"

    async def test_terms_page_renders(self, _patch_templates):
        """Terms page renders successfully."""
        request, template = _mock_request(_patch_templates)
        mock_db = AsyncMock()

        with patch(
            "routes.pages_routes.get_user_by_id", autospec=True, return_value=None
        ):
            await terms_page(request, mock_db, user_id=None)

        assert template.call_args[0][0] == "pages/terms.html"
