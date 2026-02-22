"""Smoke tests — verify every page template renders without crashing.

These tests use httpx.AsyncClient against the real FastAPI app with real
Jinja2 templates.  They mock DB-dependent services and auth but exercise
the full ASGI stack: middleware → route → template → response.

What they catch:
- Jinja2 UndefinedError (template uses a variable the route didn't pass)
- TemplateSyntaxError (broken template syntax)
- Missing template files
- Middleware ordering issues

What they DON'T test:
- HTML correctness or content
- Database queries
- Business logic (covered by unit tests)

Marked @pytest.mark.smoke so they can be run separately:
    uv run pytest -m smoke
"""

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from core.auth import optional_auth, require_auth
from core.database import get_db, get_db_readonly
from schemas import (
    CommunityAnalytics,
    DashboardData,
    PhaseDetailProgress,
    PhaseProgressData,
    PhaseSummaryData,
)

# =============================================================================
# Fixtures
# =============================================================================


def _fake_user() -> MagicMock:
    """Minimal user object that satisfies template rendering."""
    user = MagicMock()
    user.id = 1
    user.first_name = "Test"
    user.last_name = "User"
    user.github_username = "testuser"
    user.avatar_url = "https://example.com/avatar.png"
    user.is_admin = False
    user.created_at = datetime(2024, 1, 1, tzinfo=UTC)
    return user


def _fake_dashboard() -> DashboardData:
    """Minimal dashboard data for template rendering."""
    return DashboardData(
        phases=[
            PhaseSummaryData(
                id=1,
                name="Phase 1",
                slug="phase1",
                description="Learn the basics",
                short_description="Basics",
                order=1,
                topics_count=3,
                progress=PhaseProgressData(
                    steps_completed=0,
                    steps_required=10,
                    hands_on_validated=0,
                    hands_on_required=2,
                    percentage=0.0,
                    status="not_started",
                ),
            ),
        ],
        overall_percentage=0.0,
        phases_completed=0,
        total_phases=7,
        is_program_complete=False,
        continue_phase=None,
    )


def _fake_analytics() -> CommunityAnalytics:
    """Minimal analytics for status page."""
    return CommunityAnalytics(
        total_users=42,
        active_learners_30d=10,
        completion_rate=0.05,
        phase_distribution=[],
        signup_trends=[],
        verification_stats=[],
        activity_by_day=[],
        generated_at=datetime.now(UTC),
    )


@pytest_asyncio.fixture
async def anon_client():
    """HTTP client for anonymous (unauthenticated) requests.

    Mocks DB dependencies and auth to return None (anonymous user).
    Does NOT require a running database.
    """
    from main import app

    mock_db = AsyncMock()

    async def _override_get_db():
        yield mock_db

    async def _override_get_db_readonly():
        yield mock_db

    def _override_optional_auth():
        return None

    app.dependency_overrides[get_db] = _override_get_db
    app.dependency_overrides[get_db_readonly] = _override_get_db_readonly
    app.dependency_overrides[optional_auth] = _override_optional_auth

    # Mark app as initialized so /ready doesn't 503
    app.state.init_done = True
    app.state.init_error = None
    app.state.engine = MagicMock()

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client

    app.dependency_overrides.clear()


@pytest_asyncio.fixture
async def auth_client():
    """HTTP client for authenticated requests.

    Overrides auth to return user_id=1, mocks DB and user service.
    """
    from main import app

    mock_db = AsyncMock()

    async def _override_get_db():
        yield mock_db

    async def _override_get_db_readonly():
        yield mock_db

    def _override_require_auth():
        return 1

    def _override_optional_auth():
        return 1

    app.dependency_overrides[get_db] = _override_get_db
    app.dependency_overrides[get_db_readonly] = _override_get_db_readonly
    app.dependency_overrides[require_auth] = _override_require_auth
    app.dependency_overrides[optional_auth] = _override_optional_auth

    app.state.init_done = True
    app.state.init_error = None
    app.state.engine = MagicMock()
    app.state.session_maker = MagicMock()

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client

    app.dependency_overrides.clear()


# =============================================================================
# Public pages (anonymous)
# =============================================================================


@pytest.mark.smoke
class TestPublicPageSmoke:
    """Verify public page templates render without errors."""

    async def test_home_page_renders(self, anon_client: AsyncClient):
        """GET / renders the home page template."""
        response = await anon_client.get("/")
        assert response.status_code == 200
        assert "Learn to Cloud" in response.text

    async def test_curriculum_page_renders(self, anon_client: AsyncClient):
        """GET /curriculum renders the curriculum page."""
        response = await anon_client.get("/curriculum")
        assert response.status_code == 200

    async def test_faq_page_renders(self, anon_client: AsyncClient):
        """GET /faq renders the FAQ page."""
        response = await anon_client.get("/faq")
        assert response.status_code == 200

    async def test_privacy_page_renders(self, anon_client: AsyncClient):
        """GET /privacy renders the privacy page."""
        response = await anon_client.get("/privacy")
        assert response.status_code == 200

    async def test_terms_page_renders(self, anon_client: AsyncClient):
        """GET /terms renders the terms page."""
        response = await anon_client.get("/terms")
        assert response.status_code == 200

    async def test_status_page_renders(self, anon_client: AsyncClient):
        """GET /status renders with mocked health + analytics."""
        with (
            patch(
                "routes.analytics_routes.comprehensive_health_check",
                return_value={"database": True, "azure_auth": None, "pool": None},
            ),
            patch(
                "routes.analytics_routes.get_community_analytics",
                return_value=_fake_analytics(),
            ),
        ):
            response = await anon_client.get("/status")
        assert response.status_code == 200

    async def test_404_page_renders(self, anon_client: AsyncClient):
        """Unknown URL renders the 404 template (not a JSON error)."""
        response = await anon_client.get("/this-does-not-exist")
        assert response.status_code == 404


# =============================================================================
# Auth-required pages
# =============================================================================


@pytest.mark.smoke
class TestAuthPageSmoke:
    """Verify authenticated page templates render without errors."""

    async def test_dashboard_renders(self, auth_client: AsyncClient):
        """GET /dashboard renders the dashboard template."""
        with (
            patch(
                "routes.pages_routes.get_user_by_id",
                return_value=_fake_user(),
            ),
            patch(
                "routes.pages_routes.get_dashboard_data",
                return_value=_fake_dashboard(),
            ),
        ):
            response = await auth_client.get("/dashboard")
        assert response.status_code == 200

    async def test_account_renders(self, auth_client: AsyncClient):
        """GET /account renders the account settings template."""
        with patch(
            "routes.pages_routes.get_user_by_id",
            return_value=_fake_user(),
        ):
            response = await auth_client.get("/account")
        assert response.status_code == 200

    async def test_phase_page_renders(self, auth_client: AsyncClient):
        """GET /phase/1 renders the phase detail template."""
        from services.content_service import get_all_phases

        phases = get_all_phases()
        if not phases:
            pytest.skip("No content phases loaded")

        # Build a PhaseDetailProgress with empty topic progress
        detail = PhaseDetailProgress(
            topic_progress={},
            steps_completed=0,
            steps_total=0,
            percentage=0,
        )

        mock_sub_context = MagicMock()
        mock_sub_context.submissions_by_req = {}
        mock_sub_context.feedback_by_req = {}

        with (
            patch(
                "routes.pages_routes.get_user_by_id",
                return_value=_fake_user(),
            ),
            patch(
                "routes.pages_routes.get_phase_detail_progress",
                return_value=detail,
            ),
            patch(
                "routes.pages_routes.get_phase_submission_context",
                return_value=mock_sub_context,
            ),
            patch(
                "routes.pages_routes.is_phase_verification_locked",
                return_value=(False, None),
            ),
        ):
            response = await auth_client.get("/phase/1")
        assert response.status_code == 200

    async def test_topic_page_renders(self, auth_client: AsyncClient):
        """GET /phase/1/{topic_slug} renders the topic detail template."""
        from services.content_service import get_phase_by_slug

        phase = get_phase_by_slug("phase1")
        if not phase or not phase.topics:
            pytest.skip("No topics in phase1")

        topic_slug = phase.topics[0].slug

        with (
            patch(
                "routes.pages_routes.get_user_by_id",
                return_value=_fake_user(),
            ),
            patch(
                "routes.pages_routes.get_valid_completed_steps",
                return_value=[],
            ),
        ):
            response = await auth_client.get(f"/phase/1/{topic_slug}")
        assert response.status_code == 200


# =============================================================================
# Redirect behavior
# =============================================================================


@pytest.mark.smoke
class TestRedirectSmoke:
    """Verify redirect routes work through the full ASGI stack."""

    async def test_legacy_phase_redirect(self, anon_client: AsyncClient):
        """GET /phase0/old-topic redirects to /."""
        response = await anon_client.get("/phase0/old-topic", follow_redirects=False)
        assert response.status_code == 301
        assert response.headers["location"] == "/"

    async def test_auth_required_redirects_to_login(self, anon_client: AsyncClient):
        """GET /dashboard without auth redirects to /auth/login."""
        response = await anon_client.get("/dashboard", follow_redirects=False)
        assert response.status_code == 307
        assert "/auth/login" in response.headers["location"]
