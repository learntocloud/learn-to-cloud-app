"""Unit tests for HTMX routes.

Tests cover:
- POST /htmx/steps/complete — mark a step complete
- DELETE /htmx/steps/{topic_id}/{step_id} — uncomplete a step
- POST /htmx/github/submit — submit verification
- DELETE /htmx/account — delete user account

Testing approach:
- Call handlers directly with mocked dependencies
- Verify error handling branches and response headers
- HTMX-specific behavior: HX-Refresh, HX-Redirect headers
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.responses import HTMLResponse

from core.auth import AuthenticatedUser
from routes.htmx_routes import (
    htmx_complete_step,
    htmx_delete_account,
    htmx_submit_verification,
    htmx_uncomplete_step,
)
from services.steps_service import StepValidationError
from services.users_service import UserNotFoundError


def _mock_request(*, session: dict | None = None) -> MagicMock:
    """Build mock Request with session support."""
    request = MagicMock()
    request.session = session if session is not None else {}
    request.app.state.session_maker = MagicMock()

    return request


@pytest.fixture(autouse=True)
def _patch_templates():
    """Patch the templates module import for all HTMX route tests."""
    mock_templates = MagicMock()
    mock_templates.get_template.return_value.render.return_value = "<html>mock</html>"
    mock_templates.TemplateResponse = MagicMock(
        return_value=HTMLResponse("<html>mock</html>")
    )
    with patch("routes.htmx_routes.templates", mock_templates):
        yield mock_templates


@pytest.mark.unit
class TestHtmxCompleteStep:
    """Tests for POST /htmx/steps/complete."""

    async def test_complete_step_calls_service_and_renders(self):
        """Completing a step calls the service and returns HTML."""
        request = _mock_request()
        mock_db = AsyncMock()
        mock_topic = MagicMock()
        mock_step = MagicMock()
        mock_step.id = "step-1"
        mock_topic.learning_steps = [mock_step]

        with (
            patch("routes.htmx_routes.complete_step", autospec=True) as mock_complete,
            patch("routes.htmx_routes.get_topic_by_id", return_value=mock_topic),
            patch(
                "routes.htmx_routes.get_user_by_id",
                autospec=True,
                return_value=MagicMock(),
            ),
            patch(
                "routes.htmx_routes.get_valid_completed_steps",
                autospec=True,
                return_value=["step-1"],
            ),
            patch("routes.htmx_routes.build_step_data", return_value=MagicMock()),
            patch("routes.htmx_routes.build_progress_dict", return_value={}),
        ):
            result = await htmx_complete_step(
                request,
                mock_db,
                user_id=1,
                topic_id="topic-1",
                step_id="step-1",
                phase_id=1,
            )

        mock_complete.assert_awaited_once_with(mock_db, 1, "topic-1", "step-1")
        assert isinstance(result, HTMLResponse)

    async def test_complete_step_returns_hx_refresh_on_validation_error(self):
        """StepValidationError triggers HX-Refresh for stale page reload."""
        request = _mock_request()
        mock_db = AsyncMock()

        with patch(
            "routes.htmx_routes.complete_step",
            autospec=True,
            side_effect=StepValidationError("step not found"),
        ):
            result = await htmx_complete_step(
                request,
                mock_db,
                user_id=1,
                topic_id="topic-1",
                step_id="bad-step",
                phase_id=1,
            )

        assert result.headers.get("HX-Refresh") == "true"


@pytest.mark.unit
class TestHtmxUncompleteStep:
    """Tests for DELETE /htmx/steps/{topic_id}/{step_id}."""

    async def test_uncomplete_step_calls_service(self):
        """Uncompleting a step calls the service and returns HTML."""
        request = _mock_request()
        mock_db = AsyncMock()
        mock_topic = MagicMock()
        mock_step = MagicMock()
        mock_step.id = "step-1"
        mock_topic.learning_steps = [mock_step]

        with (
            patch(
                "routes.htmx_routes.uncomplete_step", autospec=True
            ) as mock_uncomplete,
            patch("routes.htmx_routes.parse_phase_id_from_topic_id", return_value=1),
            patch("routes.htmx_routes.get_topic_by_id", return_value=mock_topic),
            patch(
                "routes.htmx_routes.get_user_by_id",
                autospec=True,
                return_value=MagicMock(),
            ),
            patch(
                "routes.htmx_routes.get_valid_completed_steps",
                autospec=True,
                return_value=[],
            ),
            patch("routes.htmx_routes.build_step_data", return_value=MagicMock()),
            patch("routes.htmx_routes.build_progress_dict", return_value={}),
        ):
            result = await htmx_uncomplete_step(
                request,
                "topic-1",
                "step-1",
                mock_db,
                user_id=1,
            )

        mock_uncomplete.assert_awaited_once_with(mock_db, 1, "topic-1", "step-1")
        assert isinstance(result, HTMLResponse)

    async def test_uncomplete_step_returns_hx_refresh_on_validation_error(self):
        """StepValidationError triggers HX-Refresh."""
        request = _mock_request()
        mock_db = AsyncMock()

        with patch(
            "routes.htmx_routes.uncomplete_step",
            autospec=True,
            side_effect=StepValidationError("step not found"),
        ):
            result = await htmx_uncomplete_step(
                request,
                "topic-1",
                "bad-step",
                mock_db,
                user_id=1,
            )

        assert result.headers.get("HX-Refresh") == "true"


@pytest.mark.unit
class TestHtmxSubmitVerification:
    """Tests for POST /htmx/github/submit.

    The route is thin: derive URL, fire background task, return spinner.
    All validation errors surface via SSE, not the route itself.
    """

    async def test_submit_success_returns_processing_card(self):
        """Successful submission fires task and returns processing card."""
        request = _mock_request()
        current_user = AuthenticatedUser(user_id=1, github_username="user")

        with (
            patch("routes.htmx_routes.get_requirement_by_id", return_value=MagicMock()),
            patch(
                "routes.htmx_routes.derive_submission_value",
                autospec=True,
                return_value="test",
            ),
            patch("routes.htmx_routes.store_task"),
            patch("routes.htmx_routes.submit_validation", new_callable=AsyncMock),
            patch("routes.htmx_routes.asyncio") as mock_asyncio,
        ):
            mock_asyncio.create_task.return_value = MagicMock()
            result = await htmx_submit_verification(
                request,
                current_user,
                requirement_id="req-1",
                submitted_value="test",
            )

        # Should return a processing card, not a final result
        assert result is not None

    async def test_submit_unexpected_error_renders_server_error(self):
        """Unexpected exceptions render a server error card."""
        request = _mock_request()
        current_user = AuthenticatedUser(user_id=1, github_username="user")

        with (
            patch("routes.htmx_routes.get_requirement_by_id", return_value=MagicMock()),
            patch(
                "routes.htmx_routes.derive_submission_value",
                autospec=True,
                return_value="test",
            ),
            patch(
                "routes.htmx_routes.asyncio",
                **{"create_task.side_effect": RuntimeError("boom")},
            ),
        ):
            result = await htmx_submit_verification(
                request,
                current_user,
                requirement_id="req-1",
                submitted_value="test",
            )

        # Should render a server error card, not crash
        assert result is not None


@pytest.mark.unit
class TestHtmxDeleteAccount:
    """Tests for DELETE /htmx/account."""

    async def test_delete_account_clears_session_and_redirects(self):
        """Successful deletion clears session and sets HX-Redirect."""
        request = _mock_request(session={"user_id": 42, "github_username": "testuser"})
        mock_db = AsyncMock()

        with patch("routes.htmx_routes.delete_user_account", autospec=True):
            result = await htmx_delete_account(request, mock_db, user_id=42)

        assert result.headers.get("HX-Redirect") == "/"
        assert request.session == {}

    async def test_delete_account_returns_404_for_missing_user(self):
        """UserNotFoundError returns 404 HTML."""
        request = _mock_request(session={"user_id": 999})
        mock_db = AsyncMock()

        with patch(
            "routes.htmx_routes.delete_user_account",
            autospec=True,
            side_effect=UserNotFoundError(999),
        ):
            result = await htmx_delete_account(request, mock_db, user_id=999)

        assert result.status_code == 404
