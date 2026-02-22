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

from routes.htmx_routes import (
    htmx_complete_step,
    htmx_delete_account,
    htmx_submit_verification,
    htmx_uncomplete_step,
)
from services.steps_service import StepValidationError
from services.submissions_service import (
    AlreadyValidatedError,
    DailyLimitExceededError,
    GitHubUsernameRequiredError,
    RequirementNotFoundError,
)
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
    """Tests for POST /htmx/github/submit."""

    async def test_submit_requirement_not_found_returns_404(self):
        """RequirementNotFoundError returns 404 HTML."""
        request = _mock_request()
        mock_db = AsyncMock()

        with (
            patch(
                "routes.htmx_routes.get_user_by_id",
                autospec=True,
                return_value=MagicMock(github_username="user"),
            ),
            patch("routes.htmx_routes.get_requirement_by_id", return_value=MagicMock()),
            patch(
                "routes.htmx_routes.submit_validation",
                autospec=True,
                side_effect=RequirementNotFoundError("bad-req"),
            ),
        ):
            result = await htmx_submit_verification(
                request,
                mock_db,
                user_id=1,
                requirement_id="bad-req",
                submitted_value="test",
            )

        assert result.status_code == 404

    async def test_submit_already_validated_returns_200(self):
        """AlreadyValidatedError returns 200 with success message."""
        request = _mock_request()
        mock_db = AsyncMock()

        with (
            patch(
                "routes.htmx_routes.get_user_by_id",
                autospec=True,
                return_value=MagicMock(github_username="user"),
            ),
            patch("routes.htmx_routes.get_requirement_by_id", return_value=MagicMock()),
            patch(
                "routes.htmx_routes.submit_validation",
                autospec=True,
                side_effect=AlreadyValidatedError(),
            ),
        ):
            result = await htmx_submit_verification(
                request,
                mock_db,
                user_id=1,
                requirement_id="req-1",
                submitted_value="test",
            )

        assert result.status_code == 200

    async def test_submit_daily_limit_renders_error_banner(self):
        """DailyLimitExceededError renders card with error banner."""
        request = _mock_request()
        mock_db = AsyncMock()

        exc = DailyLimitExceededError(
            message="Daily limit exceeded",
            limit=5,
            existing_submission=MagicMock(),
        )

        with (
            patch(
                "routes.htmx_routes.get_user_by_id",
                autospec=True,
                return_value=MagicMock(github_username="user"),
            ),
            patch("routes.htmx_routes.get_requirement_by_id", return_value=MagicMock()),
            patch(
                "routes.htmx_routes.submit_validation",
                autospec=True,
                side_effect=exc,
            ),
        ):
            result = await htmx_submit_verification(
                request,
                mock_db,
                user_id=1,
                requirement_id="req-1",
                submitted_value="test",
            )

        # Should render a card (TemplateResponse), not crash
        assert result is not None

    async def test_submit_github_username_required_renders_error(self):
        """GitHubUsernameRequiredError renders card with error banner."""
        request = _mock_request()
        mock_db = AsyncMock()

        with (
            patch(
                "routes.htmx_routes.get_user_by_id",
                autospec=True,
                return_value=MagicMock(github_username=None),
            ),
            patch("routes.htmx_routes.get_requirement_by_id", return_value=MagicMock()),
            patch(
                "routes.htmx_routes.submit_validation",
                autospec=True,
                side_effect=GitHubUsernameRequiredError(),
            ),
        ):
            result = await htmx_submit_verification(
                request,
                mock_db,
                user_id=1,
                requirement_id="req-1",
                submitted_value="test",
            )

        # Should render without crashing
        assert result is not None

    async def test_submit_success_sets_hx_refresh(self):
        """Successful validation sets HX-Refresh header."""
        request = _mock_request()
        mock_db = AsyncMock()

        mock_result = MagicMock()
        mock_result.is_valid = True
        mock_result.is_server_error = False
        mock_result.submission = MagicMock()
        mock_result.task_results = []
        mock_result.message = "Passed"

        with (
            patch(
                "routes.htmx_routes.get_user_by_id",
                autospec=True,
                return_value=MagicMock(github_username="user"),
            ),
            patch("routes.htmx_routes.get_requirement_by_id", return_value=MagicMock()),
            patch(
                "routes.htmx_routes.submit_validation",
                autospec=True,
                return_value=mock_result,
            ),
            patch(
                "routes.htmx_routes.build_feedback_tasks_from_results",
                return_value=([], 0),
            ),
        ):
            result = await htmx_submit_verification(
                request,
                mock_db,
                user_id=1,
                requirement_id="req-1",
                submitted_value="test",
            )

        assert result.headers.get("HX-Refresh") == "true"

    async def test_submit_unexpected_error_renders_server_error(self):
        """Unexpected exceptions render a server error card."""
        request = _mock_request()
        mock_db = AsyncMock()

        with (
            patch(
                "routes.htmx_routes.get_user_by_id",
                autospec=True,
                return_value=MagicMock(github_username="user"),
            ),
            patch("routes.htmx_routes.get_requirement_by_id", return_value=MagicMock()),
            patch(
                "routes.htmx_routes.submit_validation",
                autospec=True,
                side_effect=RuntimeError("boom"),
            ),
        ):
            result = await htmx_submit_verification(
                request,
                mock_db,
                user_id=1,
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
