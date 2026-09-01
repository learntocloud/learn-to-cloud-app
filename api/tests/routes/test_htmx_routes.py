"""Unit tests for HTMX routes.

Tests cover:
- POST /htmx/steps/complete — mark a step complete
- DELETE /htmx/steps/{topic_id}/{step_id} — uncomplete a step
- POST /htmx/verifications/{slug}/submit/{shape} — submit verification
- DELETE /htmx/account — delete user account

Testing approach:
- Call handlers directly with mocked dependencies
- Verify error handling branches and response headers
- HTMX-specific behavior: HX-Refresh, HX-Redirect headers
"""

import logging
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from fastapi.responses import HTMLResponse
from learn_to_cloud_shared.submission_values import (
    GitHubUrlValue,
    TextValue,
    TokenValue,
)
from sqlalchemy.exc import SQLAlchemyError
from starlette.datastructures import FormData, UploadFile

from learn_to_cloud.core.auth import AuthenticatedUser
from learn_to_cloud.rendering.context import UnavailableCardContext
from learn_to_cloud.routes.htmx_routes import (
    _combine_reflection_answers,
    _submit_canonical_verification,
    htmx_complete_step,
    htmx_delete_account,
    htmx_submit_derived_verification,
    htmx_submit_reflection_verification,
    htmx_submit_value_verification,
    htmx_submit_verification,
    htmx_uncomplete_step,
    htmx_verification_attempt_status,
)
from learn_to_cloud.services.durable_verification_client import (
    DurableStatusResult,
    DurableVerificationConfigError,
    DurableVerificationStartError,
)
from learn_to_cloud.services.steps_service import StepValidationError
from learn_to_cloud.services.submissions_service import (
    VerificationAttemptSubmission,
)
from learn_to_cloud.services.users_service import UserNotFoundError
from learn_to_cloud.services.verification_status_tokens import VerificationStatusToken


def _mock_attempt_submission(*, created: bool = True) -> VerificationAttemptSubmission:
    return VerificationAttemptSubmission(attempt_id=uuid4(), created=created)


def _mock_request(
    *,
    session: dict | None = None,
    form_items: list[tuple[str, str | UploadFile]] | None = None,
) -> MagicMock:
    """Build mock Request with session support."""
    request = MagicMock()
    request.session = session if session is not None else {}
    request.app.state.session_maker = MagicMock()
    request.form = AsyncMock(return_value=FormData(form_items or []))

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
        step_uuid = uuid4()
        mock_topic = MagicMock()
        mock_step = MagicMock()
        mock_step.uuid = step_uuid
        mock_step.slug = "step-1"
        mock_topic.learning_steps = [mock_step]

        with (
            patch(
                "learn_to_cloud.routes.htmx_routes.complete_step",
                autospec=True,
                return_value=(MagicMock(), mock_topic, {step_uuid}),
            ) as mock_complete,
            patch(
                "learn_to_cloud.routes.htmx_routes.get_user_by_id",
                autospec=True,
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
                step_uuid=step_uuid,
            )

        mock_complete.assert_awaited_once_with(mock_db, 1, step_uuid)
        assert isinstance(result, HTMLResponse)

    async def test_complete_step_returns_hx_refresh_on_validation_error(self):
        """StepValidationError triggers HX-Refresh for stale page reload."""
        request = _mock_request()
        mock_db = AsyncMock()
        step_uuid = uuid4()

        with patch(
            "learn_to_cloud.routes.htmx_routes.complete_step",
            autospec=True,
            side_effect=StepValidationError("step not found"),
        ):
            result = await htmx_complete_step(
                request,
                mock_db,
                user_id=1,
                step_uuid=step_uuid,
            )

        assert result.headers.get("HX-Refresh") == "true"


@pytest.mark.unit
class TestHtmxUncompleteStep:
    """Tests for DELETE /htmx/steps/{step_uuid}."""

    async def test_uncomplete_step_calls_service(self):
        """Uncompleting a step calls the service and returns HTML."""
        request = _mock_request()
        mock_db = AsyncMock()
        step_uuid = uuid4()
        mock_topic = MagicMock()
        mock_step = MagicMock()
        mock_step.uuid = step_uuid
        mock_step.slug = "step-1"
        mock_topic.learning_steps = [mock_step]

        with (
            patch(
                "learn_to_cloud.routes.htmx_routes.uncomplete_step",
                autospec=True,
                return_value=(1, mock_topic, mock_step, set()),
            ) as mock_uncomplete,
            patch(
                "learn_to_cloud.routes.htmx_routes.get_user_by_id",
                autospec=True,
                return_value=MagicMock(),
            ),
            patch(
                "learn_to_cloud.routes.htmx_routes.build_progress_dict", return_value={}
            ),
        ):
            result = await htmx_uncomplete_step(
                request,
                step_uuid,
                mock_db,
                user_id=1,
            )

        mock_uncomplete.assert_awaited_once_with(mock_db, 1, step_uuid)
        assert isinstance(result, HTMLResponse)

    async def test_uncomplete_step_returns_hx_refresh_on_validation_error(self):
        """StepValidationError triggers HX-Refresh."""
        request = _mock_request()
        mock_db = AsyncMock()
        step_uuid = uuid4()

        with patch(
            "learn_to_cloud.routes.htmx_routes.uncomplete_step",
            autospec=True,
            side_effect=StepValidationError("step not found"),
        ):
            result = await htmx_uncomplete_step(
                request,
                step_uuid,
                mock_db,
                user_id=1,
            )

        assert result.headers.get("HX-Refresh") == "true"


@pytest.mark.unit
class TestHtmxSubmitVerification:
    """Tests for typed verification submission boundaries.

    Routes validate one form shape, then share attempt creation and startup.
    """

    async def test_derived_route_uses_server_built_url(self):
        from learn_to_cloud_shared.testing.requirement_factories import (
            profile_readme_requirement,
        )

        requirement = profile_readme_requirement(slug="profile-readme")
        request = _mock_request()
        current_user = AuthenticatedUser(user_id=1, github_username="user")

        with (
            patch(
                "learn_to_cloud.routes.htmx_routes.get_requirement_by_slug",
                return_value=requirement,
            ),
            patch(
                "learn_to_cloud.routes.htmx_routes._submit_canonical_verification",
                new_callable=AsyncMock,
                return_value=HTMLResponse("processing"),
            ) as mock_submit,
        ):
            result = await htmx_submit_derived_verification(
                request,
                current_user,
                requirement_slug="profile-readme",
            )

        assert result.status_code == 200
        mock_submit.assert_awaited_once_with(
            request,
            current_user,
            requirement,
            GitHubUrlValue("https://github.com/user/user"),
        )

    async def test_derived_route_rejects_spoofed_value(self):
        from learn_to_cloud_shared.testing.requirement_factories import (
            profile_readme_requirement,
        )

        requirement = profile_readme_requirement(slug="profile-readme")
        request = _mock_request(
            form_items=[("submitted_value", "https://github.com/other/other")]
        )
        current_user = AuthenticatedUser(user_id=1, github_username="user")

        with (
            patch(
                "learn_to_cloud.routes.htmx_routes.get_requirement_by_slug",
                return_value=requirement,
            ),
            patch(
                "learn_to_cloud.routes.htmx_routes._submit_canonical_verification",
                new_callable=AsyncMock,
            ) as mock_submit,
        ):
            result = await htmx_submit_derived_verification(
                request,
                current_user,
                requirement_slug="profile-readme",
            )

        assert result.status_code == 200
        mock_submit.assert_not_awaited()

    async def test_value_route_passes_only_submitted_value(self):
        from learn_to_cloud_shared.testing.requirement_factories import (
            ctf_token_requirement,
        )

        requirement = ctf_token_requirement(
            slug="linux-token",
            min_length=200,
        )
        token = "t" * 200
        request = _mock_request(form_items=[("submitted_value", token)])
        current_user = AuthenticatedUser(user_id=1, github_username="user")

        with (
            patch(
                "learn_to_cloud.routes.htmx_routes.get_requirement_by_slug",
                return_value=requirement,
            ),
            patch(
                "learn_to_cloud.routes.htmx_routes._submit_canonical_verification",
                new_callable=AsyncMock,
                return_value=HTMLResponse("processing"),
            ) as mock_submit,
        ):
            result = await htmx_submit_value_verification(
                request,
                current_user,
                requirement_slug="linux-token",
            )

        assert result.status_code == 200
        mock_submit.assert_awaited_once_with(
            request,
            current_user,
            requirement,
            TokenValue(token),
        )

    @pytest.mark.parametrize(
        "form_items",
        [
            [],
            [("submitted_value", "   ")],
            [("submitted_value", "t" * 200), ("answers", "unexpected")],
            [("submitted_value", "first"), ("submitted_value", "second")],
            [("submitted_value", "x")],
        ],
    )
    async def test_value_route_rejects_invalid_form_shapes(self, form_items):
        from learn_to_cloud_shared.testing.requirement_factories import (
            ctf_token_requirement,
        )

        requirement = ctf_token_requirement(
            slug="linux-token",
            min_length=200,
        )
        request = _mock_request(form_items=form_items)
        current_user = AuthenticatedUser(user_id=1, github_username="user")

        with (
            patch(
                "learn_to_cloud.routes.htmx_routes.get_requirement_by_slug",
                return_value=requirement,
            ),
            patch(
                "learn_to_cloud.routes.htmx_routes._submit_canonical_verification",
                new_callable=AsyncMock,
            ) as mock_submit,
        ):
            result = await htmx_submit_value_verification(
                request,
                current_user,
                requirement_slug="linux-token",
            )

        assert result.status_code == 200
        mock_submit.assert_not_awaited()

    async def test_reflection_route_combines_repeated_answers(self):
        from learn_to_cloud_shared.testing.requirement_factories import (
            career_reflection_requirement,
        )

        requirement = career_reflection_requirement(
            slug="career-reflection",
            min_answer_length=3,
            question_count=2,
        )
        request = _mock_request(
            form_items=[("answers", "first answer"), ("answers", "second answer")]
        )
        current_user = AuthenticatedUser(user_id=1, github_username="user")

        with (
            patch(
                "learn_to_cloud.routes.htmx_routes.get_requirement_by_slug",
                return_value=requirement,
            ),
            patch(
                "learn_to_cloud.routes.htmx_routes._submit_canonical_verification",
                new_callable=AsyncMock,
                return_value=HTMLResponse("processing"),
            ) as mock_submit,
        ):
            result = await htmx_submit_reflection_verification(
                request,
                current_user,
                requirement_slug="career-reflection",
            )

        assert result.status_code == 200
        mock_submit.assert_awaited_once()
        submitted_value = mock_submit.await_args_list[0].args[3]
        assert isinstance(submitted_value, TextValue)
        assert "## Question 0?" in submitted_value.text
        assert "first answer" in submitted_value.text
        assert "## Question 1?" in submitted_value.text
        assert "second answer" in submitted_value.text

    async def test_unknown_requirement_refreshes_stale_page(self):
        request = _mock_request()
        current_user = AuthenticatedUser(user_id=1, github_username="user")

        with patch(
            "learn_to_cloud.routes.htmx_routes.get_requirement_by_slug",
            return_value=None,
        ):
            result = await htmx_submit_derived_verification(
                request,
                current_user,
                requirement_slug="removed-requirement",
            )

        assert result.status_code == 200
        assert "location.reload()" in result.body.decode()

    async def test_legacy_route_refreshes_open_pages(self):
        result = await htmx_submit_verification(
            _mock_request(),
            AuthenticatedUser(user_id=1, github_username="user"),
        )

        assert result.status_code == 200
        assert result.headers["HX-Refresh"] == "true"

    async def test_submit_success_returns_processing_card(self):
        """Successful submission starts Durable and returns processing card."""
        request = _mock_request()
        current_user = AuthenticatedUser(user_id=1, github_username="user")
        attempt_submission = _mock_attempt_submission(created=True)
        start_result = SimpleNamespace(instance_id=str(attempt_submission.attempt_id))
        write_session = AsyncMock()
        request.app.state.session_maker.return_value.__aenter__.return_value = (
            write_session
        )

        with (
            patch(
                "learn_to_cloud.routes.htmx_routes.get_requirement_by_slug",
                return_value=MagicMock(),
            ),
            patch(
                "learn_to_cloud.routes.htmx_routes.derive_submission_value",
                autospec=True,
                return_value="https://github.com/user/repo",
            ),
            patch(
                "learn_to_cloud.routes.htmx_routes.create_verification_attempt",
                new_callable=AsyncMock,
                return_value=attempt_submission,
            ) as mock_create_attempt,
            patch(
                "learn_to_cloud.routes.htmx_routes."
                "start_verification_attempt_orchestration",
                new_callable=AsyncMock,
                return_value=start_result,
            ) as mock_start,
        ):
            result = await _submit_canonical_verification(
                request,
                current_user,
                MagicMock(slug="req-1"),
                GitHubUrlValue("https://github.com/user/repo"),
            )

        # Should return a processing card, not a final result
        assert result is not None
        mock_create_attempt.assert_awaited_once()
        mock_start.assert_awaited_once_with(attempt_submission.attempt_id)

    async def test_submit_logs_attempt_created(self, caplog):
        """A successful submission leaves an application log line (#700)."""
        request = _mock_request()
        current_user = AuthenticatedUser(user_id=1, github_username="user")
        attempt_submission = _mock_attempt_submission(created=True)

        with (
            patch(
                "learn_to_cloud.routes.htmx_routes.get_requirement_by_slug",
                return_value=MagicMock(),
            ),
            patch(
                "learn_to_cloud.routes.htmx_routes.derive_submission_value",
                autospec=True,
                return_value="https://github.com/user/repo",
            ),
            patch(
                "learn_to_cloud.routes.htmx_routes.create_verification_attempt",
                new_callable=AsyncMock,
                return_value=attempt_submission,
            ),
            patch(
                "learn_to_cloud.routes.htmx_routes."
                "start_verification_attempt_orchestration",
                new_callable=AsyncMock,
                return_value=SimpleNamespace(
                    instance_id=str(attempt_submission.attempt_id)
                ),
            ),
            caplog.at_level(logging.INFO, logger="learn_to_cloud.routes.htmx_routes"),
        ):
            await _submit_canonical_verification(
                request,
                current_user,
                MagicMock(slug="req-1"),
                GitHubUrlValue("https://github.com/user/repo"),
            )

        record = next(
            r for r in caplog.records if r.message == "verification.attempt.created"
        )
        assert record.attempt_id == str(attempt_submission.attempt_id)
        assert record.attempt_created is True
        assert record.requirement_slug == "req-1"
        assert record.user_id == 1

    async def test_submit_unexpected_error_renders_server_error(self):
        """Unexpected exceptions render a server error card."""
        request = _mock_request()
        current_user = AuthenticatedUser(user_id=1, github_username="user")

        with (
            patch(
                "learn_to_cloud.routes.htmx_routes.get_requirement_by_slug",
                return_value=MagicMock(),
            ),
            patch(
                "learn_to_cloud.routes.htmx_routes.derive_submission_value",
                autospec=True,
                return_value="test",
            ),
            patch(
                "learn_to_cloud.routes.htmx_routes.create_verification_attempt",
                new_callable=AsyncMock,
                side_effect=RuntimeError("boom"),
            ),
        ):
            result = await _submit_canonical_verification(
                request,
                current_user,
                MagicMock(slug="req-1"),
                GitHubUrlValue("https://github.com/user/user"),
            )

        # Should render a server error card, not crash
        assert result is not None

    async def test_durable_start_failure_terminalizes_attempt(self):
        """A failed pre-start attempt remains in the outcome ledger."""
        request = _mock_request()
        current_user = AuthenticatedUser(user_id=1, github_username="user")
        attempt_submission = _mock_attempt_submission(created=True)
        with (
            patch(
                "learn_to_cloud.routes.htmx_routes.get_requirement_by_slug",
                return_value=MagicMock(),
            ),
            patch(
                "learn_to_cloud.routes.htmx_routes.derive_submission_value",
                autospec=True,
                return_value="https://github.com/user/repo",
            ),
            patch(
                "learn_to_cloud.routes.htmx_routes.create_verification_attempt",
                new_callable=AsyncMock,
                return_value=attempt_submission,
            ),
            patch(
                "learn_to_cloud.routes.htmx_routes."
                "start_verification_attempt_orchestration",
                new_callable=AsyncMock,
                side_effect=DurableVerificationStartError("boom"),
            ),
            patch(
                "learn_to_cloud.routes.htmx_routes."
                "terminalize_unstarted_verification_attempt",
                new_callable=AsyncMock,
            ) as terminalize,
        ):
            result = await _submit_canonical_verification(
                request,
                current_user,
                MagicMock(slug="req-1"),
                GitHubUrlValue("https://github.com/user/repo"),
            )

        assert isinstance(result, HTMLResponse)
        terminalize.assert_awaited_once_with(
            attempt_submission.attempt_id,
            error_code="durable_transport_error",
            validation_message="Verification could not be started.",
            terminal_source="api_start_failure",
            session_maker=request.app.state.session_maker,
        )

    async def test_durable_config_error_does_not_invite_immediate_retry(
        self, _patch_templates
    ):
        """A config error is a server-side misconfiguration, so retrying never
        helps. The banner must not tell the user to try again immediately."""
        request = _mock_request()
        current_user = AuthenticatedUser(user_id=1, github_username="user")
        attempt_submission = _mock_attempt_submission(created=True)
        with (
            patch(
                "learn_to_cloud.routes.htmx_routes.get_requirement_by_slug",
                return_value=MagicMock(),
            ),
            patch(
                "learn_to_cloud.routes.htmx_routes.derive_submission_value",
                autospec=True,
                return_value="https://github.com/user/repo",
            ),
            patch(
                "learn_to_cloud.routes.htmx_routes.create_verification_attempt",
                new_callable=AsyncMock,
                return_value=attempt_submission,
            ),
            patch(
                "learn_to_cloud.routes.htmx_routes."
                "start_verification_attempt_orchestration",
                new_callable=AsyncMock,
                side_effect=DurableVerificationConfigError("not configured"),
            ),
            patch(
                "learn_to_cloud.routes.htmx_routes."
                "terminalize_unstarted_verification_attempt",
                new_callable=AsyncMock,
            ) as terminalize,
        ):
            result = await _submit_canonical_verification(
                request,
                current_user,
                MagicMock(slug="req-1"),
                GitHubUrlValue("https://github.com/user/repo"),
            )

        assert isinstance(result, HTMLResponse)
        terminalize.assert_awaited_once()
        _, _, context = _patch_templates.TemplateResponse.call_args.args
        card = context["card"]
        assert isinstance(card, UnavailableCardContext)
        assert card.retryable is False
        assert "open" in card.message.lower()
        assert "github.com/learntocloud/learn-to-cloud-app/issues" in card.message
        assert "immediately" not in card.message
        assert "team has been notified" not in card.message

    async def test_durable_start_error_invites_retry(self, _patch_templates):
        """A transient start error should still mark the banner retryable."""
        request = _mock_request()
        current_user = AuthenticatedUser(user_id=1, github_username="user")
        attempt_submission = _mock_attempt_submission(created=True)
        with (
            patch(
                "learn_to_cloud.routes.htmx_routes.get_requirement_by_slug",
                return_value=MagicMock(),
            ),
            patch(
                "learn_to_cloud.routes.htmx_routes.derive_submission_value",
                autospec=True,
                return_value="https://github.com/user/repo",
            ),
            patch(
                "learn_to_cloud.routes.htmx_routes.create_verification_attempt",
                new_callable=AsyncMock,
                return_value=attempt_submission,
            ),
            patch(
                "learn_to_cloud.routes.htmx_routes."
                "start_verification_attempt_orchestration",
                new_callable=AsyncMock,
                side_effect=DurableVerificationStartError("boom"),
            ),
            patch(
                "learn_to_cloud.routes.htmx_routes."
                "terminalize_unstarted_verification_attempt",
                new_callable=AsyncMock,
            ) as terminalize,
        ):
            await _submit_canonical_verification(
                request,
                current_user,
                MagicMock(slug="req-1"),
                GitHubUrlValue("https://github.com/user/repo"),
            )

        _, _, context = _patch_templates.TemplateResponse.call_args.args
        card = context["card"]
        assert isinstance(card, UnavailableCardContext)
        assert card.retryable is True
        terminalize.assert_awaited_once()

    async def test_async_submit_still_returns_processing_card(self):
        """Regression: async submissions must keep using the
        VerificationAttemptSubmission spinner-and-poll path."""
        request = _mock_request()
        current_user = AuthenticatedUser(user_id=1, github_username="user")
        attempt_submission = _mock_attempt_submission(created=True)
        start_result = SimpleNamespace(instance_id=str(attempt_submission.attempt_id))
        write_session = AsyncMock()
        request.app.state.session_maker.return_value.__aenter__.return_value = (
            write_session
        )

        with (
            patch(
                "learn_to_cloud.routes.htmx_routes.get_requirement_by_slug",
                return_value=MagicMock(),
            ),
            patch(
                "learn_to_cloud.routes.htmx_routes.derive_submission_value",
                autospec=True,
                return_value="https://github.com/user/repo",
            ),
            patch(
                "learn_to_cloud.routes.htmx_routes.create_verification_attempt",
                new_callable=AsyncMock,
                return_value=attempt_submission,
            ),
            patch(
                "learn_to_cloud.routes.htmx_routes."
                "start_verification_attempt_orchestration",
                new_callable=AsyncMock,
                return_value=start_result,
            ) as mock_start,
        ):
            result = await _submit_canonical_verification(
                request,
                current_user,
                MagicMock(slug="req-1"),
                GitHubUrlValue("https://github.com/user/repo"),
            )

        assert isinstance(result, HTMLResponse)
        mock_start.assert_awaited_once_with(attempt_submission.attempt_id)

    async def test_deployment_architecture_is_rejected_by_value_route(self):
        from learn_to_cloud_shared.testing.requirement_factories import (
            deployment_architecture_requirement,
        )

        requirement = deployment_architecture_requirement(
            slug="deployment-architecture",
            required_repo="learntocloud/journal-starter",
        )
        request = _mock_request(form_items=[("submitted_value", "description")])
        current_user = AuthenticatedUser(user_id=1, github_username="user")

        with (
            patch(
                "learn_to_cloud.routes.htmx_routes.get_requirement_by_slug",
                return_value=requirement,
            ),
            patch(
                "learn_to_cloud.routes.htmx_routes.create_verification_attempt",
                new_callable=AsyncMock,
            ) as mock_create,
        ):
            result = await htmx_submit_value_verification(
                request,
                current_user,
                requirement_slug="deployment-architecture",
            )

        assert isinstance(result, HTMLResponse)
        mock_create.assert_not_awaited()

    async def test_deployment_architecture_is_rejected_by_reflection_route(self):
        from learn_to_cloud_shared.testing.requirement_factories import (
            deployment_architecture_requirement,
        )

        requirement = deployment_architecture_requirement(
            slug="deployment-architecture",
            required_repo="learntocloud/journal-starter",
        )
        request = _mock_request(form_items=[("answers", "description")])
        current_user = AuthenticatedUser(user_id=1, github_username="user")

        with (
            patch(
                "learn_to_cloud.routes.htmx_routes.get_requirement_by_slug",
                return_value=requirement,
            ),
            patch(
                "learn_to_cloud.routes.htmx_routes.create_verification_attempt",
                new_callable=AsyncMock,
            ) as mock_create,
        ):
            result = await htmx_submit_reflection_verification(
                request,
                current_user,
                requirement_slug="deployment-architecture",
            )

        assert isinstance(result, HTMLResponse)
        mock_create.assert_not_awaited()

    async def test_duplicate_submit_skips_durable_start(self):
        """When ``create_verification_attempt`` returns ``created=False``
        (concurrent submit raced into the same attempt), the route does
        NOT call ``start_verification_attempt_orchestration`` — the
        original submit already kicked off Durable, and calling start_new
        again with the same instance id would error."""
        request = _mock_request()
        current_user = AuthenticatedUser(user_id=1, github_username="user")
        attempt_submission = _mock_attempt_submission(created=False)

        with (
            patch(
                "learn_to_cloud.routes.htmx_routes.get_requirement_by_slug",
                return_value=MagicMock(),
            ),
            patch(
                "learn_to_cloud.routes.htmx_routes.derive_submission_value",
                autospec=True,
                return_value="https://github.com/user/repo",
            ),
            patch(
                "learn_to_cloud.routes.htmx_routes.create_verification_attempt",
                new_callable=AsyncMock,
                return_value=attempt_submission,
            ),
            patch(
                "learn_to_cloud.routes.htmx_routes."
                "start_verification_attempt_orchestration",
                new_callable=AsyncMock,
            ) as mock_start,
        ):
            result = await _submit_canonical_verification(
                request,
                current_user,
                MagicMock(slug="req-1"),
                GitHubUrlValue("https://github.com/user/repo"),
            )

        assert isinstance(result, HTMLResponse)
        mock_start.assert_not_awaited()


@pytest.mark.unit
class TestHtmxVerificationAttemptStatus:
    """Tests for Durable-backed verification status polling."""

    async def test_running_status_returns_next_poll_card(self):
        request = _mock_request()
        current_user = AuthenticatedUser(user_id=1, github_username="user")
        token_data = VerificationStatusToken(
            user_id=1,
            job_id=str(uuid4()),
            instance_id=str(uuid4()),
            requirement_slug="req-1",
        )

        with (
            patch(
                "learn_to_cloud.routes.htmx_routes.load_verification_status_token",
                return_value=token_data,
            ) as mock_load_token,
            patch(
                "learn_to_cloud.routes.htmx_routes.get_verification_attempt_status",
                new_callable=AsyncMock,
                return_value=DurableStatusResult(runtime_status="Running"),
            ) as mock_get_status,
            patch(
                "learn_to_cloud.routes.htmx_routes.get_requirement_by_slug",
                return_value=MagicMock(),
            ),
        ):
            result = await htmx_verification_attempt_status(
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
            requirement_slug="req-1",
        )

        with (
            patch(
                "learn_to_cloud.routes.htmx_routes.load_verification_status_token",
                return_value=token_data,
            ),
            patch(
                "learn_to_cloud.routes.htmx_routes.get_verification_attempt_status",
                new_callable=AsyncMock,
                return_value=DurableStatusResult(runtime_status="Completed"),
            ),
            patch(
                "learn_to_cloud.routes.htmx_routes.VerificationAttemptRepository",
                autospec=True,
            ) as mock_repository_class,
        ):
            mock_repository_class.return_value.get_terminal_state = AsyncMock(
                return_value=None
            )
            result = await htmx_verification_attempt_status(
                request,
                token="signed-token",
                current_user=current_user,
            )

        assert isinstance(result, HTMLResponse)
        assert "location.reload()" in bytes(result.body).decode()

    async def test_completed_status_logs_terminal_outcome(self, caplog):
        """The poller records the attempt's terminal outcome (#700)."""
        request = _mock_request()
        request.app.state.session_maker.return_value.__aenter__.return_value = (
            AsyncMock()
        )
        current_user = AuthenticatedUser(user_id=1, github_username="user")
        job_id = uuid4()
        token_data = VerificationStatusToken(
            user_id=1,
            job_id=str(job_id),
            instance_id=str(uuid4()),
            requirement_slug="journal-api-implementation",
        )

        with (
            patch(
                "learn_to_cloud.routes.htmx_routes.load_verification_status_token",
                return_value=token_data,
            ),
            patch(
                "learn_to_cloud.routes.htmx_routes.get_verification_attempt_status",
                new_callable=AsyncMock,
                return_value=DurableStatusResult(runtime_status="Completed"),
            ),
            patch(
                "learn_to_cloud.routes.htmx_routes.VerificationAttemptRepository",
                autospec=True,
            ) as mock_repository_class,
            caplog.at_level(logging.INFO, logger="learn_to_cloud.routes.htmx_routes"),
        ):
            mock_repository_class.return_value.get_terminal_state = AsyncMock(
                return_value=SimpleNamespace(
                    id=job_id,
                    outcome="server_error",
                    error_code="verification_incomplete",
                    validation_message="boom",
                    terminal_source="orchestrator",
                    completed_at=None,
                )
            )
            await htmx_verification_attempt_status(
                request,
                token="signed-token",
                current_user=current_user,
            )

        record = next(
            r for r in caplog.records if r.message == "verification.attempt.observed"
        )
        # A server_error is the case an operator most needs to find, so it must
        # not be buried at INFO.
        assert record.levelno == logging.WARNING
        assert record.outcome == "server_error"
        assert record.error_code == "verification_incomplete"
        assert record.attempt_id == str(job_id)
        assert record.requirement_slug == "journal-api-implementation"

    async def test_completed_status_survives_log_read_failure(self):
        """A logging read failure must not break the learner's page reload."""
        request = _mock_request()
        current_user = AuthenticatedUser(user_id=1, github_username="user")
        token_data = VerificationStatusToken(
            user_id=1,
            job_id=str(uuid4()),
            instance_id=str(uuid4()),
            requirement_slug="req-1",
        )

        with (
            patch(
                "learn_to_cloud.routes.htmx_routes.load_verification_status_token",
                return_value=token_data,
            ),
            patch(
                "learn_to_cloud.routes.htmx_routes.get_verification_attempt_status",
                new_callable=AsyncMock,
                return_value=DurableStatusResult(runtime_status="Completed"),
            ),
            patch(
                "learn_to_cloud.routes.htmx_routes.VerificationAttemptRepository",
                autospec=True,
            ) as mock_repository_class,
        ):
            mock_repository_class.return_value.get_terminal_state = AsyncMock(
                side_effect=SQLAlchemyError("connection lost")
            )
            result = await htmx_verification_attempt_status(
                request,
                token="signed-token",
                current_user=current_user,
            )

        assert isinstance(result, HTMLResponse)
        assert "location.reload()" in bytes(result.body).decode()

    async def test_failed_status_terminalizes_attempt_and_renders_error(
        self,
        _patch_templates,
    ):
        """Durable terminal failure records a server error and renders it."""
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
            requirement_slug="req-1",
        )

        with (
            patch(
                "learn_to_cloud.routes.htmx_routes.load_verification_status_token",
                return_value=token_data,
            ),
            patch(
                "learn_to_cloud.routes.htmx_routes.get_verification_attempt_status",
                new_callable=AsyncMock,
                return_value=DurableStatusResult(runtime_status="Failed"),
            ),
            patch(
                "learn_to_cloud.routes.htmx_routes.VerificationAttemptRepository",
                autospec=True,
            ) as mock_repository_class,
            patch(
                "learn_to_cloud.routes.htmx_routes.terminalize_verification_attempt",
                new_callable=AsyncMock,
                return_value=MagicMock(
                    won=True,
                    state=MagicMock(outcome="server_error"),
                ),
            ) as terminalize,
            patch(
                "learn_to_cloud.routes.htmx_routes.get_requirement_by_slug",
                return_value=MagicMock(),
            ),
        ):
            mock_repository = mock_repository_class.return_value
            mock_repository.get_status = AsyncMock(return_value=MagicMock())
            result = await htmx_verification_attempt_status(
                request,
                token="signed-token",
                current_user=current_user,
            )

        assert isinstance(result, HTMLResponse)
        terminalize.assert_awaited_once_with(
            job_id,
            outcome="server_error",
            error_code="server_error",
            validation_message="Verification failed before recording a result.",
            terminal_source="poller",
            session_maker=request.app.state.session_maker,
        )
        _, _, context = _patch_templates.TemplateResponse.call_args.args
        card = context["card"]
        assert isinstance(card, UnavailableCardContext)
        assert card.retryable is False
        assert (
            card.message
            == "Verification failed because the verification service hit an internal "
            "error. Please try again in a few minutes. If it keeps failing, open an "
            "issue at https://github.com/learntocloud/learn-to-cloud-app/issues."
        )

    async def test_canceled_status_terminalizes_attempt_as_cancelled(self):
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
            requirement_slug="req-1",
        )

        with (
            patch(
                "learn_to_cloud.routes.htmx_routes.load_verification_status_token",
                return_value=token_data,
            ),
            patch(
                "learn_to_cloud.routes.htmx_routes.get_verification_attempt_status",
                new_callable=AsyncMock,
                return_value=DurableStatusResult(runtime_status="Canceled"),
            ),
            patch(
                "learn_to_cloud.routes.htmx_routes.VerificationAttemptRepository",
                autospec=True,
            ) as mock_repository_class,
            patch(
                "learn_to_cloud.routes.htmx_routes.terminalize_verification_attempt",
                new_callable=AsyncMock,
                return_value=MagicMock(
                    won=True,
                    state=MagicMock(outcome="cancelled"),
                ),
            ) as terminalize,
            patch(
                "learn_to_cloud.routes.htmx_routes.get_requirement_by_slug",
                return_value=MagicMock(),
            ),
        ):
            mock_repository = mock_repository_class.return_value
            mock_repository.get_status = AsyncMock(return_value=MagicMock())
            result = await htmx_verification_attempt_status(
                request,
                token="signed-token",
                current_user=current_user,
            )

        assert isinstance(result, HTMLResponse)
        terminalize.assert_awaited_once_with(
            job_id,
            outcome="cancelled",
            error_code="cancelled",
            validation_message="Verification was cancelled.",
            terminal_source="poller",
            session_maker=request.app.state.session_maker,
        )

    async def test_failed_status_reloads_when_attempt_was_already_finalized(self):
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
            requirement_slug="req-1",
        )

        with (
            patch(
                "learn_to_cloud.routes.htmx_routes.load_verification_status_token",
                return_value=token_data,
            ),
            patch(
                "learn_to_cloud.routes.htmx_routes.get_verification_attempt_status",
                new_callable=AsyncMock,
                return_value=DurableStatusResult(runtime_status="Failed"),
            ),
            patch(
                "learn_to_cloud.routes.htmx_routes.VerificationAttemptRepository",
                autospec=True,
            ) as mock_attempt_repository_class,
            patch(
                "learn_to_cloud.routes.htmx_routes.terminalize_verification_attempt",
                new_callable=AsyncMock,
                return_value=MagicMock(
                    won=False,
                    state=MagicMock(outcome="succeeded"),
                ),
            ),
        ):
            attempt_repo = mock_attempt_repository_class.return_value
            attempt_repo.get_status = AsyncMock(return_value=MagicMock())

            result = await htmx_verification_attempt_status(
                request,
                token="signed-token",
                current_user=current_user,
            )

        assert "location.reload()" in bytes(result.body).decode()
        mock_session.commit.assert_not_awaited()

    async def test_failed_status_reloads_when_attempt_is_missing(self):
        request = _mock_request()
        mock_session = AsyncMock()
        request.app.state.session_maker.return_value.__aenter__.return_value = (
            mock_session
        )
        current_user = AuthenticatedUser(user_id=1, github_username="user")
        token_data = VerificationStatusToken(
            user_id=1,
            job_id=str(uuid4()),
            instance_id=str(uuid4()),
            requirement_slug="req-1",
        )

        with (
            patch(
                "learn_to_cloud.routes.htmx_routes.load_verification_status_token",
                return_value=token_data,
            ),
            patch(
                "learn_to_cloud.routes.htmx_routes.get_verification_attempt_status",
                new_callable=AsyncMock,
                return_value=DurableStatusResult(runtime_status="Failed"),
            ),
            patch(
                "learn_to_cloud.routes.htmx_routes.VerificationAttemptRepository",
                autospec=True,
            ) as mock_attempt_repository_class,
        ):
            mock_attempt_repository_class.return_value.get_status = AsyncMock(
                return_value=None
            )

            result = await htmx_verification_attempt_status(
                request,
                token="signed-token",
                current_user=current_user,
            )

        assert isinstance(result, HTMLResponse)
        assert "location.reload()" in bytes(result.body).decode()


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


class TestCombineReflectionAnswers:
    """Unit tests for the career reflection answer combiner."""

    @staticmethod
    def _requirement(min_answer_length: int = 10, question_count: int = 3):
        from learn_to_cloud_shared.testing.requirement_factories import (
            career_reflection_requirement,
        )

        return career_reflection_requirement(
            min_answer_length=min_answer_length,
            question_count=question_count,
        )

    def test_combines_answers_with_question_headers(self):
        requirement = self._requirement(min_answer_length=5, question_count=2)
        combined = _combine_reflection_answers(
            requirement,
            ["First answer body", "Second answer body"],
        )

        assert "## Question 0?" in combined
        assert "First answer body" in combined
        assert "## Question 1?" in combined
        assert "Second answer body" in combined

    def test_rejects_wrong_number_of_answers(self):
        requirement = self._requirement(question_count=3)
        with pytest.raises(ValueError, match="all of the reflection questions"):
            _combine_reflection_answers(requirement, ["only one answer"])

    def test_rejects_answer_below_minimum_length(self):
        requirement = self._requirement(min_answer_length=50, question_count=1)
        with pytest.raises(ValueError, match="at least 50 characters"):
            _combine_reflection_answers(requirement, ["too short"])

    def test_rejects_answer_above_maximum_length(self):
        requirement = self._requirement(min_answer_length=1, question_count=1)
        with pytest.raises(ValueError, match="too long"):
            _combine_reflection_answers(requirement, ["x" * 6001])

    def test_strips_whitespace_before_validating(self):
        requirement = self._requirement(min_answer_length=5, question_count=1)
        with pytest.raises(ValueError, match="at least 5 characters"):
            _combine_reflection_answers(requirement, ["   a   "])
