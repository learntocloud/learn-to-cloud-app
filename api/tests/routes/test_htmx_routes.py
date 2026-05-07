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

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from fastapi.responses import HTMLResponse

from learn_to_cloud.core.auth import AuthenticatedUser
from learn_to_cloud.routes.htmx_routes import (
    htmx_complete_step,
    htmx_delete_account,
    htmx_submit_verification,
    htmx_uncomplete_step,
    htmx_verification_job_status,
)
from learn_to_cloud.services.durable_verification_client import DurableStatusResult
from learn_to_cloud.services.steps_service import StepValidationError
from learn_to_cloud.services.users_service import UserNotFoundError
from learn_to_cloud.services.verification_status_tokens import VerificationStatusToken


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
    with patch("learn_to_cloud.routes.htmx_routes.templates", mock_templates):
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
            patch(
                "learn_to_cloud.routes.htmx_routes.complete_step", autospec=True
            ) as mock_complete,
            patch(
                "learn_to_cloud.routes.htmx_routes.get_topic_by_id",
                return_value=mock_topic,
            ),
            patch(
                "learn_to_cloud.routes.htmx_routes.get_user_by_id",
                autospec=True,
                return_value=MagicMock(),
            ),
            patch(
                "learn_to_cloud.routes.htmx_routes.get_valid_completed_steps",
                autospec=True,
                return_value=["step-1"],
            ),
            patch(
                "learn_to_cloud.routes.htmx_routes.build_step_data",
                return_value=MagicMock(),
            ),
            patch(
                "learn_to_cloud.routes.htmx_routes.build_progress_dict", return_value={}
            ),
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
            "learn_to_cloud.routes.htmx_routes.complete_step",
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
                "learn_to_cloud.routes.htmx_routes.uncomplete_step", autospec=True
            ) as mock_uncomplete,
            patch(
                "learn_to_cloud.routes.htmx_routes.parse_phase_id_from_topic_id",
                return_value=1,
            ),
            patch(
                "learn_to_cloud.routes.htmx_routes.get_topic_by_id",
                return_value=mock_topic,
            ),
            patch(
                "learn_to_cloud.routes.htmx_routes.get_user_by_id",
                autospec=True,
                return_value=MagicMock(),
            ),
            patch(
                "learn_to_cloud.routes.htmx_routes.get_valid_completed_steps",
                autospec=True,
                return_value=[],
            ),
            patch(
                "learn_to_cloud.routes.htmx_routes.build_step_data",
                return_value=MagicMock(),
            ),
            patch(
                "learn_to_cloud.routes.htmx_routes.build_progress_dict", return_value={}
            ),
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
            "learn_to_cloud.routes.htmx_routes.uncomplete_step",
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

    The route is thin: derive URL, persist a job, start Durable, return spinner.
    """

    async def test_submit_success_returns_processing_card(self):
        """Successful submission starts Durable and returns processing card."""
        request = _mock_request()
        current_user = AuthenticatedUser(user_id=1, github_username="user")
        job = SimpleNamespace(id=uuid4(), orchestration_instance_id=None)
        job_submission = SimpleNamespace(job=job, created=True)
        start_result = SimpleNamespace(instance_id=str(job.id))
        write_session = AsyncMock()
        request.app.state.session_maker.return_value.__aenter__.return_value = (
            write_session
        )
        repo = MagicMock()
        repo.mark_starting = AsyncMock()

        with (
            patch(
                "learn_to_cloud.routes.htmx_routes.get_requirement_by_id",
                return_value=MagicMock(),
            ),
            patch(
                "learn_to_cloud.routes.htmx_routes.derive_submission_value",
                autospec=True,
                return_value="test",
            ),
            patch(
                "learn_to_cloud.routes.htmx_routes.create_verification_job",
                new_callable=AsyncMock,
                return_value=job_submission,
            ) as mock_create_job,
            patch(
                "learn_to_cloud.routes.htmx_routes.start_verification_orchestration",
                new_callable=AsyncMock,
                return_value=start_result,
            ) as mock_start,
            patch(
                "learn_to_cloud.routes.htmx_routes.VerificationJobRepository",
                return_value=repo,
            ),
        ):
            result = await htmx_submit_verification(
                request,
                current_user,
                requirement_id="req-1",
                submitted_value="test",
            )

        # Should return a processing card, not a final result
        assert result is not None
        mock_create_job.assert_awaited_once()
        mock_start.assert_awaited_once_with(job.id)
        repo.mark_starting.assert_awaited_once_with(job.id, start_result.instance_id)
        write_session.commit.assert_awaited_once()

    async def test_submit_unexpected_error_renders_server_error(self):
        """Unexpected exceptions render a server error card."""
        request = _mock_request()
        current_user = AuthenticatedUser(user_id=1, github_username="user")

        with (
            patch(
                "learn_to_cloud.routes.htmx_routes.get_requirement_by_id",
                return_value=MagicMock(),
            ),
            patch(
                "learn_to_cloud.routes.htmx_routes.derive_submission_value",
                autospec=True,
                return_value="test",
            ),
            patch(
                "learn_to_cloud.routes.htmx_routes.create_verification_job",
                new_callable=AsyncMock,
                side_effect=RuntimeError("boom"),
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
class TestHtmxVerificationJobStatus:
    """Tests for Durable-backed verification status polling."""

    async def test_running_status_returns_next_poll_card(self):
        request = _mock_request()
        current_user = AuthenticatedUser(user_id=1, github_username="user")
        token_data = VerificationStatusToken(
            user_id=1,
            job_id=str(uuid4()),
            instance_id=str(uuid4()),
            requirement_id="req-1",
        )

        with (
            patch(
                "learn_to_cloud.routes.htmx_routes.load_verification_status_token",
                return_value=token_data,
            ) as mock_load_token,
            patch(
                "learn_to_cloud.routes.htmx_routes.get_verification_orchestration_status",
                new_callable=AsyncMock,
                return_value=DurableStatusResult(runtime_status="Running"),
            ) as mock_get_status,
            patch(
                "learn_to_cloud.routes.htmx_routes.get_requirement_by_id",
                return_value=MagicMock(),
            ),
        ):
            result = await htmx_verification_job_status(
                request,
                token="signed-token",
                current_user=current_user,
            )

        assert isinstance(result, HTMLResponse)
        mock_load_token.assert_called_once_with(
            "signed-token",
            expected_user_id=1,
        )
        mock_get_status.assert_awaited_once_with(token_data.instance_id)

    async def test_completed_status_returns_reload_trigger(self):
        request = _mock_request()
        current_user = AuthenticatedUser(user_id=1, github_username="user")
        token_data = VerificationStatusToken(
            user_id=1,
            job_id=str(uuid4()),
            instance_id=str(uuid4()),
            requirement_id="req-1",
        )

        with (
            patch(
                "learn_to_cloud.routes.htmx_routes.load_verification_status_token",
                return_value=token_data,
            ),
            patch(
                "learn_to_cloud.routes.htmx_routes.get_verification_orchestration_status",
                new_callable=AsyncMock,
                return_value=DurableStatusResult(runtime_status="Completed"),
            ),
        ):
            result = await htmx_verification_job_status(
                request,
                token="signed-token",
                current_user=current_user,
            )

        assert isinstance(result, HTMLResponse)
        assert "location.reload()" in bytes(result.body).decode()

    async def test_failed_status_marks_job_server_error(self):
        request = _mock_request()
        mock_session = AsyncMock()
        request.app.state.session_maker.return_value.__aenter__.return_value = (
            mock_session
        )
        current_user = AuthenticatedUser(user_id=1, github_username="user")
        job_id = uuid4()
        token_data = VerificationStatusToken(
            user_id=1,
            job_id=str(job_id),
            instance_id=str(uuid4()),
            requirement_id="req-1",
        )

        with (
            patch(
                "learn_to_cloud.routes.htmx_routes.load_verification_status_token",
                return_value=token_data,
            ),
            patch(
                "learn_to_cloud.routes.htmx_routes.get_verification_orchestration_status",
                new_callable=AsyncMock,
                return_value=DurableStatusResult(runtime_status="Failed"),
            ),
            patch(
                "learn_to_cloud.routes.htmx_routes.VerificationJobRepository",
                autospec=True,
            ) as mock_repository_class,
        ):
            result = await htmx_verification_job_status(
                request,
                token="signed-token",
                current_user=current_user,
            )

        assert isinstance(result, HTMLResponse)
        mock_repository = mock_repository_class.return_value
        mock_repository.mark_server_error.assert_awaited_once()
        assert mock_repository.mark_server_error.await_args.args == (job_id,)
        mock_session.commit.assert_awaited_once()


@pytest.mark.unit
class TestHtmxDeleteAccount:
    """Tests for DELETE /htmx/account."""

    async def test_delete_account_clears_session_and_redirects(self):
        """Successful deletion clears session and sets HX-Redirect."""
        request = _mock_request(session={"user_id": 42, "github_username": "testuser"})
        mock_db = AsyncMock()

        with patch(
            "learn_to_cloud.routes.htmx_routes.delete_user_account", autospec=True
        ):
            result = await htmx_delete_account(request, mock_db, user_id=42)

        assert result.headers.get("HX-Redirect") == "/"
        assert request.session == {}

    async def test_delete_account_returns_404_for_missing_user(self):
        """UserNotFoundError returns 404 HTML."""
        request = _mock_request(session={"user_id": 999})
        mock_db = AsyncMock()

        with patch(
            "learn_to_cloud.routes.htmx_routes.delete_user_account",
            autospec=True,
            side_effect=UserNotFoundError(999),
        ):
            result = await htmx_delete_account(request, mock_db, user_id=999)

        assert result.status_code == 404
