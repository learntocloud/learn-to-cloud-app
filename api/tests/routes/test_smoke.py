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
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
import pytest_asyncio
from fastapi.responses import HTMLResponse
from httpx import ASGITransport, AsyncClient
from learn_to_cloud_shared.core.database import get_db, get_db_readonly
from learn_to_cloud_shared.schemas import (
    DashboardData,
    LearningProgress,
    PhaseProgress,
    PhaseProgressData,
    PhaseSummaryData,
    VerificationProgress,
)

from learn_to_cloud.core.auth import (
    AuthenticatedUser,
    optional_authenticated_user,
    require_authenticated_user,
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
                order=1,
                name="Phase 1",
                slug="phase1",
                progress=PhaseProgressData(
                    learning=LearningProgress(steps_completed=0, steps_required=10),
                    verification=VerificationProgress(
                        requirements_verified=0, requirements_required=2
                    ),
                    is_complete=False,
                    status="not_started",
                ),
            ),
        ],
        learning_percentage=0.0,
        verification_percentage=0.0,
        phases_completed=0,
        total_phases=7,
        is_program_complete=False,
        continue_phase=None,
    )


@pytest_asyncio.fixture
async def _patched_content():
    """Route smoke tests don't run against a real DB; redirect content reads
    to the authored YAML loader so routes get a real curriculum tree."""
    from learn_to_cloud_shared.content_yaml_loader import (
        get_all_phases_from_yaml,
    )
    from learn_to_cloud_shared.schemas import PhaseOverview, TopicOverview

    yaml_phases = get_all_phases_from_yaml()
    yaml_overview = tuple(
        PhaseOverview(
            uuid=phase.uuid,
            order=phase.order,
            name=phase.name,
            slug=phase.slug,
            description=phase.description,
            short_description=phase.short_description,
            topics=[
                TopicOverview(uuid=t.uuid, slug=t.slug, name=t.name)
                for t in phase.topics
            ],
        )
        for phase in yaml_phases
    )

    def _curriculum_overview():
        return yaml_overview

    def _phase_by_slug(slug):
        return next((p for p in yaml_phases if p.slug == slug), None)

    with (
        patch(
            "learn_to_cloud.routes.pages_routes.get_curriculum_overview",
            side_effect=_curriculum_overview,
        ),
        patch(
            "learn_to_cloud.routes.pages_routes.get_phase_by_slug",
            side_effect=_phase_by_slug,
        ),
    ):
        yield yaml_phases


@pytest_asyncio.fixture
async def anon_client(_patched_content):
    """HTTP client for anonymous (unauthenticated) requests.

    Mocks DB dependencies and auth to return None (anonymous user).
    Does NOT require a running database.
    """
    from learn_to_cloud.main import app

    mock_db = AsyncMock()

    async def _override_get_db():
        yield mock_db

    async def _override_get_db_readonly():
        yield mock_db

    def _override_optional_user():
        return None

    app.dependency_overrides[get_db] = _override_get_db
    app.dependency_overrides[get_db_readonly] = _override_get_db_readonly
    app.dependency_overrides[optional_authenticated_user] = _override_optional_user

    # Mark app as initialized so /ready doesn't 503
    app.state.init_done = True
    app.state.init_error = None
    app.state.engine = MagicMock()

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client

    app.dependency_overrides.clear()


@pytest_asyncio.fixture
async def auth_client(_patched_content):
    """HTTP client for authenticated requests.

    Overrides auth to return an identity, mocks DB and user service.
    """
    from learn_to_cloud.main import app

    mock_db = AsyncMock()

    async def _override_get_db():
        yield mock_db

    async def _override_get_db_readonly():
        yield mock_db

    def _override_current_user():
        return AuthenticatedUser(user_id=1, github_username="testuser")

    app.dependency_overrides[get_db] = _override_get_db
    app.dependency_overrides[get_db_readonly] = _override_get_db_readonly
    app.dependency_overrides[optional_authenticated_user] = _override_current_user
    app.dependency_overrides[require_authenticated_user] = _override_current_user

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
        assert "Information is now abundant." in response.text
        assert "Access to education should be too." in response.text
        assert "Free, open-source cloud engineering education." in response.text
        assert "high agency, self-sufficiency, and discipline." in response.text
        assert (
            "Cloud resources and some learning materials may cost extra."
            not in response.text
        )
        assert "Build an AI-powered API," in response.text
        assert "AI-powered journal" not in response.text
        assert "Structure, feedback, and real-world relevance." in response.text
        assert (
            response.text.index("Learn with direction.")
            < response.text.index("Improve with feedback.")
            < response.text.index("Learn what's current.")
        )
        assert "People working in the field continually update" in response.text
        assert "Build with purpose." not in response.text
        assert "automated checks and AI-assisted reviews" in response.text
        assert "Build it. Then take it further." in response.text

    async def test_curriculum_page_renders(self, anon_client: AsyncClient):
        """GET /curriculum renders the phase hierarchy and progress CTA."""
        response = await anon_client.get("/curriculum")
        assert response.status_code == 200
        assert "The complete cloud curriculum." in response.text
        assert "Learn in sequence." in response.text
        assert "Keep your place as you learn." in response.text

    @pytest.mark.parametrize("path", ["/faq", "/privacy", "/terms"])
    async def test_public_page_renders(self, anon_client: AsyncClient, path: str):
        response = await anon_client.get(path)
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
                "learn_to_cloud.routes.pages_routes.get_user_by_id",
                return_value=_fake_user(),
            ),
            patch(
                "learn_to_cloud.routes.pages_routes.get_dashboard_data",
                return_value=_fake_dashboard(),
            ),
        ):
            response = await auth_client.get("/dashboard")
        assert response.status_code == 200

    async def test_account_renders(self, auth_client: AsyncClient):
        """GET /account renders the account settings template."""
        with patch(
            "learn_to_cloud.routes.pages_routes.get_user_by_id",
            return_value=_fake_user(),
        ):
            response = await auth_client.get("/account")
        assert response.status_code == 200

    async def test_typed_verification_submission_routes_bind_forms(
        self, auth_client: AsyncClient
    ):
        from learn_to_cloud_shared.testing.requirement_factories import (
            career_reflection_requirement,
            ctf_token_requirement,
            profile_readme_requirement,
        )

        requirements = {
            "profile-readme": profile_readme_requirement(slug="profile-readme"),
            "linux-token": ctf_token_requirement(
                slug="linux-token",
                min_length=200,
            ),
            "career-reflection": career_reflection_requirement(
                slug="career-reflection",
                min_answer_length=3,
                question_count=2,
            ),
        }

        with (
            patch(
                "learn_to_cloud.routes.htmx_routes.get_requirement_by_slug",
                side_effect=requirements.get,
            ),
            patch(
                "learn_to_cloud.routes.htmx_routes._submit_canonical_verification",
                new_callable=AsyncMock,
                return_value=HTMLResponse("processing"),
            ) as mock_submit,
        ):
            derived = await auth_client.post(
                "/htmx/verifications/profile-readme/submit/derived"
            )
            value = await auth_client.post(
                "/htmx/verifications/linux-token/submit/value",
                data={"submitted_value": "t" * 200},
            )
            reflection = await auth_client.post(
                "/htmx/verifications/career-reflection/submit/reflection",
                content="answers=first+answer&answers=second+answer",
                headers={"Content-Type": "application/x-www-form-urlencoded"},
            )

        assert derived.status_code == 200
        assert value.status_code == 200
        assert reflection.status_code == 200
        assert mock_submit.await_count == 3

    async def test_phase_page_renders(self, auth_client: AsyncClient):
        """GET /phase/1 renders the phase detail template."""
        from learn_to_cloud_shared.content_yaml_loader import (
            get_all_phases_from_yaml,
        )

        phases = get_all_phases_from_yaml()
        if not phases:
            pytest.skip("No content phases loaded")

        # Build a PhaseProgress with empty topic progress
        detail = PhaseProgress(
            phase_id=1,
            learning=LearningProgress(steps_completed=0, steps_required=0),
            verification=VerificationProgress(
                requirements_verified=0, requirements_required=0
            ),
            topic_progress={},
        )

        with (
            patch(
                "learn_to_cloud.routes.pages_routes.get_user_by_id",
                return_value=_fake_user(),
            ),
            patch(
                "learn_to_cloud.routes.pages_routes.fetch_phase_progress",
                return_value=detail,
            ),
        ):
            response = await auth_client.get("/phase/1")
        assert response.status_code == 200

    async def test_verifications_page_renders(self, auth_client: AsyncClient):
        """GET /verifications renders the workspace hub."""
        phase = SimpleNamespace(
            phase=SimpleNamespace(order=1, name="Phase 1"),
            progress=VerificationProgress(
                requirements_verified=0,
                requirements_required=1,
            ),
            status="not_started",
            is_locked=False,
            prerequisite_phase_id=None,
        )
        overview = SimpleNamespace(
            phases=[phase],
            requirements_verified=0,
            requirements_required=1,
            percentage=0.0,
            is_complete=False,
            next_phase=phase,
        )

        with (
            patch(
                "learn_to_cloud.routes.pages_routes.get_user_by_id",
                return_value=_fake_user(),
            ),
            patch(
                "learn_to_cloud.routes.pages_routes.get_verifications_overview",
                return_value=overview,
            ),
        ):
            response = await auth_client.get("/verifications")

        assert response.status_code == 200
        assert "Verification workspace" in response.text
        assert 'href="/verifications/phase/1"' in response.text

    async def test_phase_verification_page_shows_feedback(
        self, auth_client: AsyncClient
    ):
        """A passed requirement still surfaces its rubric feedback (the why)."""
        from datetime import UTC, datetime

        from learn_to_cloud_shared.content_yaml_loader import (
            get_all_phases_from_yaml,
        )
        from learn_to_cloud_shared.schemas import SubmissionData

        from learn_to_cloud.rendering.context import (
            build_requirement_card_context,
            feedback_tasks_and_passed,
        )

        phase = next(
            (p for p in get_all_phases_from_yaml() if p.slug == "phase1"), None
        )
        if not phase or not phase.hands_on_verification:
            pytest.skip("No hands-on requirements in phase1")
        req_slug = phase.hands_on_verification.requirements[0].slug

        verified_submission = SubmissionData(
            id=uuid4(),
            submitted_value="https://github.com/testuser/repo",
            is_validated=True,
            validated_at=datetime(2024, 1, 2, tzinfo=UTC),
            verification_completed=True,
            created_at=datetime(2024, 1, 2, tzinfo=UTC),
        )
        requirement = phase.hands_on_verification.requirements[0]
        feedback_tasks, feedback_passed = feedback_tasks_and_passed(
            {
                "tasks": [
                    {
                        "name": "Reflection depth",
                        "passed": True,
                        "message": "You clearly explained what you explored.",
                        "next_steps": "",
                    }
                ],
                "passed": 1,
            }
        )

        detail = PhaseProgress(
            phase_id=1,
            learning=LearningProgress(steps_completed=0, steps_required=0),
            verification=VerificationProgress(
                requirements_verified=1, requirements_required=1
            ),
            topic_progress={},
        )
        workspace = SimpleNamespace(
            phase=phase,
            phase_progress=detail,
            requirements=[requirement],
            card_contexts_by_req={
                req_slug: build_requirement_card_context(
                    requirement=requirement,
                    github_username="testuser",
                    submission=verified_submission,
                    feedback_tasks=feedback_tasks,
                    feedback_passed=feedback_passed,
                )
            },
            verification_locked=False,
            prerequisite_phase_id=None,
            history=SimpleNamespace(
                items=[],
                page=1,
                has_previous=False,
                has_next=False,
            ),
        )

        with (
            patch(
                "learn_to_cloud.routes.pages_routes.get_user_by_id",
                return_value=_fake_user(),
            ),
            patch(
                "learn_to_cloud.routes.pages_routes.get_phase_verification_workspace",
                return_value=workspace,
            ),
        ):
            response = await auth_client.get("/verifications/phase/1")

        assert response.status_code == 200
        assert "Review summary" in response.text
        assert "You clearly explained what you explored." in response.text

    async def test_topic_page_renders(self, auth_client: AsyncClient):
        """GET /phase/1/{topic_slug} renders the topic detail template."""
        from learn_to_cloud_shared.content_yaml_loader import (
            get_all_phases_from_yaml,
        )

        phase = next(
            (p for p in get_all_phases_from_yaml() if p.slug == "phase1"), None
        )
        if not phase or not phase.topics:
            pytest.skip("No topics in phase1")

        topic_slug = phase.topics[0].slug

        with (
            patch(
                "learn_to_cloud.routes.pages_routes.get_user_by_id",
                return_value=_fake_user(),
            ),
            patch(
                "learn_to_cloud.routes.pages_routes.get_valid_completed_steps",
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

    @pytest.mark.parametrize(
        "path",
        ["/dashboard", "/verifications", "/verifications/phase/1"],
    )
    async def test_auth_required_redirects_to_login(
        self,
        anon_client: AsyncClient,
        path: str,
    ):
        """Authenticated pages redirect anonymous visitors to login."""
        response = await anon_client.get(path, follow_redirects=False)
        assert response.status_code == 303
        assert "/auth/login" in response.headers["location"]
