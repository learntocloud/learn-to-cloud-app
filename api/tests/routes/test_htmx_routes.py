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
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from fastapi.responses import HTMLResponse
from learn_to_cloud_shared.models import User
from learn_to_cloud_shared.repositories.verification_attempt_repository import (
    AttemptStatusRow,
)
from learn_to_cloud_shared.submission_values import (
    GitHubUrlValue,
    TextValue,
    TokenValue,
)
from sqlalchemy.exc import SQLAlchemyError
from starlette.datastructures import FormData, UploadFile

from learn_to_cloud.core.auth import AuthenticatedUser, AuthenticationRequired
from learn_to_cloud.rendering.requirement_cards import CheckingCardContext
from learn_to_cloud.routes.htmx_routes import (
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
from learn_to_cloud.services.steps_service import StepValidationError
from learn_to_cloud.services.submissions_service import (
    VerificationAttemptSubmission,
)
from learn_to_cloud.verification_forms import combine_reflection_answers


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
    with patch(
        "learn_to_cloud.rendering.htmx_responses.templates",
        mock_templates,
    ):
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
        account = User(id=1, github_username="user")

        with (
            patch(
                "learn_to_cloud.routes.htmx_routes.complete_step",
                autospec=True,
                return_value=(MagicMock(), mock_topic, {step_uuid}),
            ) as mock_complete,
            patch(
                "learn_to_cloud.routes.htmx_routes.render_step_toggle",
                autospec=True,
                return_value=HTMLResponse("<html>mock</html>"),
            ) as mock_render,
        ):
            result = await htmx_complete_step(
                request,
                mock_db,
                account=account,
                step_uuid=step_uuid,
            )

        mock_complete.assert_awaited_once_with(mock_db, 1, step_uuid)
        mock_render.assert_called_once_with(
            request, account, mock_topic, mock_step, {step_uuid}
        )
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
                account=User(id=1, github_username="user"),
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
        account = User(id=1, github_username="user")

        with (
            patch(
                "learn_to_cloud.routes.htmx_routes.uncomplete_step",
                autospec=True,
                return_value=(1, mock_topic, mock_step, set()),
            ) as mock_uncomplete,
            patch(
                "learn_to_cloud.routes.htmx_routes.render_step_toggle",
                autospec=True,
                return_value=HTMLResponse("<html>mock</html>"),
            ) as mock_render,
        ):
            result = await htmx_uncomplete_step(
                request,
                step_uuid,
                mock_db,
                account=account,
            )

        mock_uncomplete.assert_awaited_once_with(mock_db, 1, step_uuid)
        mock_render.assert_called_once_with(
            request, account, mock_topic, mock_step, set()
        )
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
                account=User(id=1, github_username="user"),
            )

        assert result.headers.get("HX-Refresh") == "true"


@pytest.mark.unit
class TestHtmxSubmitVerification:
    """Tests for typed verification submission boundaries.

    Routes validate one form shape, then share persisted attempt creation.
    """

    async def test_derived_route_uses_server_built_url(self):
        from learn_to_cloud_shared_test_support.requirement_factories import (
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
        from learn_to_cloud_shared_test_support.requirement_factories import (
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
        from learn_to_cloud_shared_test_support.requirement_factories import (
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
        from learn_to_cloud_shared_test_support.requirement_factories import (
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
        from learn_to_cloud_shared_test_support.requirement_factories import (
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
        assert "location.reload()" in bytes(result.body).decode()

    async def test_legacy_route_refreshes_open_pages(self):
        result = await htmx_submit_verification()

        assert result.status_code == 200
        assert result.headers["HX-Refresh"] == "true"

    @pytest.mark.parametrize("created", [True, False])
    async def test_submit_returns_queued_attempt_without_external_calls(
        self, created, _patch_templates
    ):
        request = _mock_request()
        current_user = AuthenticatedUser(user_id=1, github_username="user")
        attempt_submission = _mock_attempt_submission(created=created)

        with (
            patch(
                "learn_to_cloud.services.verification_attempt_service.create_verification_attempt",
                new_callable=AsyncMock,
                return_value=attempt_submission,
            ) as mock_create_attempt,
            patch(
                "httpx.AsyncClient",
                side_effect=AssertionError("Submission must not start external work"),
            ) as mock_http_client,
        ):
            result = await _submit_canonical_verification(
                request,
                current_user,
                MagicMock(slug="req-1"),
                GitHubUrlValue("https://github.com/user/repo"),
            )

        assert result.status_code == 200
        mock_create_attempt.assert_awaited_once_with(
            session_maker=request.app.state.session_maker,
            user_id=1,
            github_username="user",
            requirement_slug="req-1",
            submitted_value=GitHubUrlValue("https://github.com/user/repo"),
        )
        mock_http_client.assert_not_called()
        _, _, context = _patch_templates.TemplateResponse.call_args.args
        card = context["card"]
        assert isinstance(card, CheckingCardContext)
        assert card.verification_attempt_id == attempt_submission.attempt_id
        assert card.verification_status_delay_seconds == 2

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
                "learn_to_cloud.services.verification_attempt_service.create_verification_attempt",
                new_callable=AsyncMock,
                return_value=attempt_submission,
            ),
            caplog.at_level(
                logging.INFO,
                logger="learn_to_cloud.services.verification_attempt_service",
            ),
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
        assert record.__dict__["verification.attempt.id"] == str(
            attempt_submission.attempt_id
        )
        assert record.__dict__["verification.attempt.created"] is True
        assert record.__dict__["verification.requirement.slug"] == "req-1"
        assert "user_id" not in record.__dict__

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
                "learn_to_cloud.services.verification_attempt_service.create_verification_attempt",
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

    @pytest.mark.parametrize("error_type", [SQLAlchemyError, ConnectionRefusedError])
    async def test_submit_database_unavailable_returns_503(
        self, error_type, _patch_templates, caplog
    ):
        request = _mock_request()
        current_user = AuthenticatedUser(user_id=1, github_username="user")
        with (
            patch(
                "learn_to_cloud.services.verification_attempt_service.create_verification_attempt",
                new_callable=AsyncMock,
                side_effect=error_type("private database details"),
            ),
            caplog.at_level(logging.WARNING),
        ):
            result = await _submit_canonical_verification(
                request,
                current_user,
                MagicMock(slug="req-1"),
                GitHubUrlValue("https://github.com/user/repo"),
            )

        assert result.status_code == 503
        assert b"private database details" not in result.body
        assert "private database details" not in caplog.text
        _patch_templates.TemplateResponse.assert_not_called()

    async def test_repo_fork_is_rejected_by_value_route(self):
        from learn_to_cloud_shared_test_support.requirement_factories import (
            repo_fork_requirement,
        )

        requirement = repo_fork_requirement(
            slug="repo-fork",
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
                "learn_to_cloud.services.verification_attempt_service.create_verification_attempt",
                new_callable=AsyncMock,
            ) as mock_create,
        ):
            result = await htmx_submit_value_verification(
                request,
                current_user,
                requirement_slug="repo-fork",
            )

        assert isinstance(result, HTMLResponse)
        mock_create.assert_not_awaited()

    async def test_repo_fork_is_rejected_by_reflection_route(self):
        from learn_to_cloud_shared_test_support.requirement_factories import (
            repo_fork_requirement,
        )

        requirement = repo_fork_requirement(
            slug="repo-fork",
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
                "learn_to_cloud.services.verification_attempt_service.create_verification_attempt",
                new_callable=AsyncMock,
            ) as mock_create,
        ):
            result = await htmx_submit_reflection_verification(
                request,
                current_user,
                requirement_slug="repo-fork",
            )

        assert isinstance(result, HTMLResponse)
        mock_create.assert_not_awaited()


@pytest.mark.unit
class TestHtmxVerificationAttemptStatus:
    """Polling uses owned database state without writing outcomes."""

    @pytest.mark.parametrize("started", [False, True])
    async def test_active_attempt_returns_next_poll_card(
        self, started, _patch_templates
    ):
        request = _mock_request()
        attempt = self._attempt(started=started)
        requirement = MagicMock(slug="req-1")

        with (
            patch(
                "learn_to_cloud.services.verification_attempt_service.VerificationAttemptRepository",
                autospec=True,
            ) as repository,
            patch(
                "learn_to_cloud.routes.htmx_routes.get_curriculum_catalog",
                return_value=SimpleNamespace(
                    requirements_by_uuid={attempt.requirement_uuid: requirement}
                ),
            ),
            patch("httpx.AsyncClient") as http_client,
        ):
            repository.return_value.get_status.return_value = attempt
            result = await htmx_verification_attempt_status(
                request,
                attempt_id=attempt.id,
                current_user=AuthenticatedUser(user_id=1, github_username="user"),
            )

        assert result.status_code == 200
        repository.return_value.get_status.assert_awaited_once_with(attempt.id)
        assert len(repository.return_value.mock_calls) == 1
        http_client.assert_not_called()
        _, _, context = _patch_templates.TemplateResponse.call_args.args
        card = context["card"]
        assert isinstance(card, CheckingCardContext)
        assert card.requirement is requirement
        assert card.verification_attempt_id == attempt.id
        assert card.verification_status_delay_seconds == 5

    @pytest.mark.parametrize(
        ("outcome", "status_code"),
        [
            ("succeeded", 200),
            ("failed", 200),
            ("server_error", 200),
            ("cancelled", 200),
            ("unrecognized", 409),
        ],
    )
    async def test_terminal_and_unexpected_states_do_not_write_or_invent_success(
        self, outcome, status_code, _patch_templates
    ):
        request = _mock_request()
        session = AsyncMock()
        request.app.state.session_maker.return_value.__aenter__.return_value = session
        attempt = self._attempt(outcome=outcome)
        with patch(
            "learn_to_cloud.services.verification_attempt_service.VerificationAttemptRepository",
            autospec=True,
        ) as repository:
            repository.return_value.get_status.return_value = attempt
            result = await htmx_verification_attempt_status(
                request,
                attempt_id=attempt.id,
                current_user=AuthenticatedUser(user_id=1, github_username="user"),
            )

        assert result.status_code == status_code
        assert (b"location.reload()" in result.body) is (status_code == 200)
        assert len(repository.return_value.mock_calls) == 1
        session.commit.assert_not_awaited()
        _patch_templates.TemplateResponse.assert_not_called()

    @pytest.mark.parametrize("outcome", [None, "succeeded", "server_error"])
    async def test_unknown_and_other_users_attempts_return_identical_404(
        self, outcome, _patch_templates
    ):
        request = _mock_request()
        attempt = self._attempt(user_id=2, outcome=outcome)
        with (
            patch(
                "learn_to_cloud.services.verification_attempt_service.VerificationAttemptRepository",
                autospec=True,
            ) as repository,
            patch(
                "learn_to_cloud.routes.htmx_routes.get_curriculum_catalog"
            ) as catalog,
        ):
            repository.return_value.get_status.side_effect = [None, attempt]
            responses = [
                await htmx_verification_attempt_status(
                    request,
                    attempt_id=attempt.id,
                    current_user=AuthenticatedUser(user_id=1, github_username="user"),
                )
                for _ in range(2)
            ]

        assert [response.status_code for response in responses] == [404, 404]
        assert responses[0].body == responses[1].body
        assert b"location.reload()" not in responses[0].body
        assert str(attempt.id).encode() not in responses[0].body
        catalog.assert_not_called()
        _patch_templates.TemplateResponse.assert_not_called()

    @pytest.mark.parametrize("error_type", [SQLAlchemyError, ConnectionRefusedError])
    async def test_database_unavailable_returns_503_not_reload(
        self, error_type, caplog, _patch_templates
    ):
        request = _mock_request()
        with (
            patch(
                "learn_to_cloud.services.verification_attempt_service.VerificationAttemptRepository",
                autospec=True,
            ) as repository,
            caplog.at_level(logging.WARNING),
        ):
            repository.return_value.get_status.side_effect = error_type(
                "private database details"
            )
            result = await htmx_verification_attempt_status(
                request,
                attempt_id=uuid4(),
                current_user=AuthenticatedUser(user_id=1, github_username="user"),
            )

        assert result.status_code == 503
        assert b"location.reload()" not in result.body
        assert b"private database details" not in result.body
        assert "private database details" not in caplog.text
        record = next(
            r
            for r in caplog.records
            if r.message == "verification.status.database_unavailable"
        )
        assert record.__dict__["error.type"] == error_type.__name__
        assert record.exc_info is None
        _patch_templates.TemplateResponse.assert_not_called()

    @pytest.mark.parametrize(
        ("query", "status_code"),
        [
            ("attempt_id=00000000-0000-0000-0000-000000000001", 404),
            ("attempt_id=invalid", 422),
            ("token=retired-token", 422),
            ("", 422),
        ],
    )
    async def test_http_requires_uuid_attempt_id(self, query, status_code):
        from uuid import UUID

        from fastapi import FastAPI
        from httpx import ASGITransport, AsyncClient

        from learn_to_cloud.core.auth import require_authenticated_user
        from learn_to_cloud.routes.htmx_routes import router

        app = FastAPI()
        app.include_router(router)
        app.state.session_maker = MagicMock()
        app.dependency_overrides[require_authenticated_user] = lambda: (
            AuthenticatedUser(user_id=1, github_username="user")
        )
        with patch(
            "learn_to_cloud.services.verification_attempt_service.VerificationAttemptRepository",
            autospec=True,
        ) as repository:
            repository.return_value.get_status.return_value = None
            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as client:
                response = await client.get(
                    f"/htmx/verification/attempts/status?{query}"
                )

        assert response.status_code == status_code
        if status_code == 404:
            repository.return_value.get_status.assert_awaited_once_with(
                UUID("00000000-0000-0000-0000-000000000001")
            )
        else:
            repository.assert_not_called()

    @staticmethod
    def _attempt(*, user_id=1, outcome=None, started=False):
        now = datetime.now(UTC)
        return AttemptStatusRow(
            id=uuid4(),
            user_id=user_id,
            requirement_uuid=uuid4(),
            outcome=outcome,
            started_at=now if started else None,
            created_at=now,
        )


@pytest.mark.unit
class TestHtmxDeleteAccount:
    """Tests for DELETE /htmx/account."""

    async def test_delete_account_clears_session_and_redirects(self):
        """Successful deletion clears session and sets HX-Redirect."""
        request = _mock_request(session={"user_id": 42, "github_username": "testuser"})
        with patch(
            "learn_to_cloud.routes.htmx_routes.mutate_account", autospec=True
        ) as mutate:
            result = await htmx_delete_account(
                request, current_user=AuthenticatedUser(42, "testuser")
            )

        assert result.headers.get("HX-Redirect") == "/"
        mutate.assert_awaited_once_with(request, 42, delete_account=True)

    async def test_delete_account_rechecks_authorization(self):
        """Deletion recheck failures stay unauthorized."""
        request = _mock_request(session={"user_id": 999})

        with (
            patch(
                "learn_to_cloud.routes.htmx_routes.mutate_account",
                autospec=True,
                side_effect=AuthenticationRequired(),
            ),
            pytest.raises(AuthenticationRequired),
        ):
            await htmx_delete_account(
                request, current_user=AuthenticatedUser(999, "testuser")
            )


class TestCombineReflectionAnswers:
    """Unit tests for the career reflection answer combiner."""

    @staticmethod
    def _requirement(min_answer_length: int = 10, question_count: int = 3):
        from learn_to_cloud_shared_test_support.requirement_factories import (
            career_reflection_requirement,
        )

        return career_reflection_requirement(
            min_answer_length=min_answer_length,
            question_count=question_count,
        )

    def test_combines_answers_with_question_headers(self):
        requirement = self._requirement(min_answer_length=5, question_count=2)
        combined = combine_reflection_answers(
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
            combine_reflection_answers(requirement, ["only one answer"])

    def test_rejects_answer_below_minimum_length(self):
        requirement = self._requirement(min_answer_length=50, question_count=1)
        with pytest.raises(ValueError, match="at least 50 characters"):
            combine_reflection_answers(requirement, ["too short"])

    def test_rejects_answer_above_maximum_length(self):
        requirement = self._requirement(min_answer_length=1, question_count=1)
        with pytest.raises(ValueError, match="too long"):
            combine_reflection_answers(requirement, ["x" * 6001])

    def test_strips_whitespace_before_validating(self):
        requirement = self._requirement(min_answer_length=5, question_count=1)
        with pytest.raises(ValueError, match="at least 5 characters"):
            combine_reflection_answers(requirement, ["   a   "])
