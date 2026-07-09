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
from typing import cast
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from fastapi.responses import HTMLResponse
from learn_to_cloud_shared.models import SubmissionValueKind, VerificationJob
from learn_to_cloud_shared.schemas import SubmissionResult

from learn_to_cloud.core.auth import AuthenticatedUser
from learn_to_cloud.routes.htmx_routes import (
    _combine_reflection_answers,
    htmx_complete_step,
    htmx_delete_account,
    htmx_submit_verification,
    htmx_uncomplete_step,
    htmx_verification_job_status,
)
from learn_to_cloud.services.durable_verification_client import (
    DurableStatusResult,
    DurableVerificationConfigError,
    DurableVerificationStartError,
)
from learn_to_cloud.services.steps_service import StepValidationError
from learn_to_cloud.services.submissions_service import (
    SyncVerificationResult,
    VerificationJobSubmission,
)
from learn_to_cloud.services.users_service import UserNotFoundError
from learn_to_cloud.services.verification_status_tokens import VerificationStatusToken


def _async_requirement():
    """A real HandsOnRequirement for tests that need to build a
    PreparedVerificationJob payload alongside a VerificationJobSubmission."""
    from learn_to_cloud_shared.testing.requirement_factories import (
        journal_api_verifier_requirement,
    )

    return journal_api_verifier_requirement(
        slug="journal-api-implementation",
        name="Journal API",
        description="Test",
    )


def _mock_job(value: str = "https://github.com/user/repo") -> SimpleNamespace:
    return SimpleNamespace(
        id=uuid4(),
        orchestration_instance_id=None,
        submitted_value=value,
        submission_value_kind=SubmissionValueKind.GITHUB_URL.value,
        github_url=value,
        token_value=None,
        deployed_url=None,
        text_value=None,
    )


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
    """Tests for POST /htmx/github/submit.

    The route is thin: derive URL, persist a job, start Durable, return spinner.
    """

    async def test_submit_success_returns_processing_card(self):
        """Successful submission starts Durable and returns processing card."""
        request = _mock_request()
        current_user = AuthenticatedUser(user_id=1, github_username="user")
        job = _mock_job()
        job_submission = SimpleNamespace(
            job=job,
            created=True,
            requirement=_async_requirement(),
            github_username="user",
        )
        start_result = SimpleNamespace(instance_id=str(job.id))
        write_session = AsyncMock()
        request.app.state.session_maker.return_value.__aenter__.return_value = (
            write_session
        )
        repo = MagicMock()

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
                AsyncMock(),
                current_user,
                requirement_slug="req-1",
                submitted_value="https://github.com/user/repo",
            )

        # Should return a processing card, not a final result
        assert result is not None
        mock_create_job.assert_awaited_once()
        mock_start.assert_awaited_once()

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
                "learn_to_cloud.routes.htmx_routes.create_verification_job",
                new_callable=AsyncMock,
                side_effect=RuntimeError("boom"),
            ),
        ):
            result = await htmx_submit_verification(
                request,
                AsyncMock(),
                current_user,
                requirement_slug="req-1",
                submitted_value="test",
            )

        # Should render a server error card, not crash
        assert result is not None

    async def test_durable_start_failure_deletes_job(self):
        """When Durable's start_new fails, the route deletes the just-
        created job row instead of marking it server_error. Frees the
        partial unique index so the user can retry immediately."""
        request = _mock_request()
        current_user = AuthenticatedUser(user_id=1, github_username="user")
        job = _mock_job()
        async_result = VerificationJobSubmission(
            job=cast(VerificationJob, job),
            created=True,
            requirement=_async_requirement(),
            github_username="user",
        )
        write_session = AsyncMock()
        request.app.state.session_maker.return_value.__aenter__.return_value = (
            write_session
        )
        repo = MagicMock()
        repo.delete_active = AsyncMock(return_value=True)

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
                "learn_to_cloud.routes.htmx_routes.create_verification_job",
                new_callable=AsyncMock,
                return_value=async_result,
            ),
            patch(
                "learn_to_cloud.routes.htmx_routes.start_verification_orchestration",
                new_callable=AsyncMock,
                side_effect=DurableVerificationStartError("boom"),
            ),
            patch(
                "learn_to_cloud.routes.htmx_routes.VerificationJobRepository",
                return_value=repo,
            ),
        ):
            result = await htmx_submit_verification(
                request,
                AsyncMock(),
                current_user,
                requirement_slug="req-1",
                submitted_value="https://github.com/user/repo",
            )

        assert isinstance(result, HTMLResponse)
        repo.delete_active.assert_awaited_once_with(job.id)
        write_session.commit.assert_awaited_once()

    async def test_durable_config_error_does_not_invite_immediate_retry(
        self, _patch_templates
    ):
        """A config error is a server-side misconfiguration, so retrying never
        helps. The banner must not tell the user to try again immediately."""
        request = _mock_request()
        current_user = AuthenticatedUser(user_id=1, github_username="user")
        job = _mock_job()
        async_result = VerificationJobSubmission(
            job=cast(VerificationJob, job),
            created=True,
            requirement=_async_requirement(),
            github_username="user",
        )
        write_session = AsyncMock()
        request.app.state.session_maker.return_value.__aenter__.return_value = (
            write_session
        )
        repo = MagicMock()
        repo.delete_active = AsyncMock(return_value=True)

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
                "learn_to_cloud.routes.htmx_routes.create_verification_job",
                new_callable=AsyncMock,
                return_value=async_result,
            ),
            patch(
                "learn_to_cloud.routes.htmx_routes.start_verification_orchestration",
                new_callable=AsyncMock,
                side_effect=DurableVerificationConfigError("not configured"),
            ),
            patch(
                "learn_to_cloud.routes.htmx_routes.VerificationJobRepository",
                return_value=repo,
            ),
        ):
            result = await htmx_submit_verification(
                request,
                AsyncMock(),
                current_user,
                requirement_slug="req-1",
                submitted_value="https://github.com/user/repo",
            )

        assert isinstance(result, HTMLResponse)
        # The in-flight slot is still freed so a later (post-fix) retry works.
        repo.delete_active.assert_awaited_once_with(job.id)
        _, _, context = _patch_templates.TemplateResponse.call_args.args
        assert context["server_error"] is True
        assert context["server_error_retryable"] is False
        assert "open" in context["server_error_message"].lower()
        assert (
            "github.com/learntocloud/learn-to-cloud-app/issues"
            in context["server_error_message"]
        )
        assert "immediately" not in context["server_error_message"]
        assert "team has been notified" not in context["server_error_message"]

    async def test_durable_start_error_invites_retry(self, _patch_templates):
        """A transient start error should still mark the banner retryable."""
        request = _mock_request()
        current_user = AuthenticatedUser(user_id=1, github_username="user")
        job = _mock_job()
        async_result = VerificationJobSubmission(
            job=cast(VerificationJob, job),
            created=True,
            requirement=_async_requirement(),
            github_username="user",
        )
        write_session = AsyncMock()
        request.app.state.session_maker.return_value.__aenter__.return_value = (
            write_session
        )
        repo = MagicMock()
        repo.delete_active = AsyncMock(return_value=True)

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
                "learn_to_cloud.routes.htmx_routes.create_verification_job",
                new_callable=AsyncMock,
                return_value=async_result,
            ),
            patch(
                "learn_to_cloud.routes.htmx_routes.start_verification_orchestration",
                new_callable=AsyncMock,
                side_effect=DurableVerificationStartError("boom"),
            ),
            patch(
                "learn_to_cloud.routes.htmx_routes.VerificationJobRepository",
                return_value=repo,
            ),
        ):
            await htmx_submit_verification(
                request,
                AsyncMock(),
                current_user,
                requirement_slug="req-1",
                submitted_value="https://github.com/user/repo",
            )

        _, _, context = _patch_templates.TemplateResponse.call_args.args
        assert context["server_error"] is True
        assert context["server_error_retryable"] is True

    async def test_sync_submit_returns_reload_trigger(self):
        """Sync submission types finish in-request and return a page-reload
        snippet so the next requirement re-renders with fresh server state."""
        request = _mock_request()
        current_user = AuthenticatedUser(user_id=1, github_username="user")
        submission = SimpleNamespace(
            id=42,
            requirement_slug="req-1",
            submission_type=SimpleNamespace(value="github_profile"),
            verification_completed=True,
        )
        sync_result = SyncVerificationResult(
            submission_result=cast(
                SubmissionResult,
                SimpleNamespace(
                    submission=submission,
                    is_valid=True,
                    is_server_error=False,
                ),
            ),
        )

        with (
            patch(
                "learn_to_cloud.routes.htmx_routes.get_requirement_by_slug",
                return_value=MagicMock(),
            ),
            patch(
                "learn_to_cloud.routes.htmx_routes.derive_submission_value",
                autospec=True,
                return_value="https://github.com/user",
            ),
            patch(
                "learn_to_cloud.routes.htmx_routes.create_verification_job",
                new_callable=AsyncMock,
                return_value=sync_result,
            ) as mock_create_job,
            patch(
                "learn_to_cloud.routes.htmx_routes.start_verification_orchestration",
                new_callable=AsyncMock,
            ) as mock_start,
            patch(
                "learn_to_cloud.routes.htmx_routes.VerificationJobRepository",
            ) as mock_repo_class,
        ):
            result = await htmx_submit_verification(
                request,
                AsyncMock(),
                current_user,
                requirement_slug="req-1",
                submitted_value="https://github.com/user",
            )

        assert isinstance(result, HTMLResponse)
        # Page reload trigger (matches the async terminal pattern).
        assert "location.reload()" in bytes(result.body).decode()
        # Critical: sync path must never touch Durable or VerificationJob.
        mock_start.assert_not_awaited()
        mock_repo_class.assert_not_called()
        mock_create_job.assert_awaited_once()

    async def test_sync_submit_failure_also_returns_reload_trigger(self):
        """A failed sync verification still reloads so the failed card is
        re-rendered from the persisted Submission state."""
        request = _mock_request()
        current_user = AuthenticatedUser(user_id=1, github_username="user")
        submission = SimpleNamespace(
            id=43,
            requirement_slug="req-1",
            submission_type=SimpleNamespace(value="github_profile"),
            verification_completed=True,
        )
        sync_result = SyncVerificationResult(
            submission_result=cast(
                SubmissionResult,
                SimpleNamespace(
                    submission=submission,
                    is_valid=False,
                    is_server_error=False,
                ),
            ),
        )

        with (
            patch(
                "learn_to_cloud.routes.htmx_routes.get_requirement_by_slug",
                return_value=MagicMock(),
            ),
            patch(
                "learn_to_cloud.routes.htmx_routes.derive_submission_value",
                autospec=True,
                return_value="https://github.com/user",
            ),
            patch(
                "learn_to_cloud.routes.htmx_routes.create_verification_job",
                new_callable=AsyncMock,
                return_value=sync_result,
            ),
        ):
            result = await htmx_submit_verification(
                request,
                AsyncMock(),
                current_user,
                requirement_slug="req-1",
                submitted_value="https://github.com/user",
            )

        assert isinstance(result, HTMLResponse)
        assert "location.reload()" in bytes(result.body).decode()

    async def test_async_submit_still_returns_processing_card(self):
        """Regression: async submissions must keep using the
        VerificationJobSubmission spinner-and-poll path."""
        request = _mock_request()
        current_user = AuthenticatedUser(user_id=1, github_username="user")
        job = _mock_job()
        async_result = VerificationJobSubmission(
            job=cast(VerificationJob, job),
            created=True,
            requirement=_async_requirement(),
            github_username="user",
        )
        start_result = SimpleNamespace(instance_id=str(job.id))
        write_session = AsyncMock()
        request.app.state.session_maker.return_value.__aenter__.return_value = (
            write_session
        )
        repo = MagicMock()

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
                "learn_to_cloud.routes.htmx_routes.create_verification_job",
                new_callable=AsyncMock,
                return_value=async_result,
            ),
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
                AsyncMock(),
                current_user,
                requirement_slug="req-1",
                submitted_value="https://github.com/user/repo",
            )

        assert isinstance(result, HTMLResponse)
        mock_start.assert_awaited_once()
        await_args = mock_start.await_args
        assert await_args is not None
        (call_arg,) = await_args.args
        assert call_arg.id == job.id

    async def test_deployment_architecture_long_description_reaches_derive(self):
        """A >2048-char architecture description must not be truncated by the
        shared ``submitted_value`` cap; it flows via ``architecture_description``
        into ``derive_submission_value`` intact and starts an orchestration."""
        from learn_to_cloud_shared.testing.requirement_factories import (
            deployment_architecture_requirement,
        )

        requirement = deployment_architecture_requirement(
            slug="deployment-architecture",
            required_repo="learntocloud/journal-starter",
        )
        long_description = "A detailed two-tier deployment description. " * 100
        assert len(long_description) > 2048

        request = _mock_request()
        current_user = AuthenticatedUser(user_id=1, github_username="user")
        job = _mock_job()
        async_result = VerificationJobSubmission(
            job=cast(VerificationJob, job),
            created=True,
            requirement=requirement,
            github_username="user",
        )
        start_result = SimpleNamespace(instance_id=str(job.id))
        write_session = AsyncMock()
        request.app.state.session_maker.return_value.__aenter__.return_value = (
            write_session
        )

        with (
            patch(
                "learn_to_cloud.routes.htmx_routes.get_requirement_by_slug",
                return_value=requirement,
            ),
            patch(
                "learn_to_cloud.routes.htmx_routes.derive_submission_value",
                autospec=True,
                return_value=long_description,
            ) as mock_derive,
            patch(
                "learn_to_cloud.routes.htmx_routes.create_verification_job",
                new_callable=AsyncMock,
                return_value=async_result,
            ),
            patch(
                "learn_to_cloud.routes.htmx_routes.start_verification_orchestration",
                new_callable=AsyncMock,
                return_value=start_result,
            ) as mock_start,
            patch(
                "learn_to_cloud.routes.htmx_routes.VerificationJobRepository",
                return_value=MagicMock(),
            ),
        ):
            result = await htmx_submit_verification(
                request,
                AsyncMock(),
                current_user,
                requirement_slug="deployment-architecture",
                architecture_description=long_description,
            )

        assert isinstance(result, HTMLResponse)
        mock_start.assert_awaited_once()
        derive_kwargs = mock_derive.call_args.kwargs
        assert derive_kwargs["user_input"] == long_description.strip()

    async def test_deployment_architecture_empty_description_shows_error(self):
        from learn_to_cloud_shared.testing.requirement_factories import (
            deployment_architecture_requirement,
        )

        requirement = deployment_architecture_requirement(
            slug="deployment-architecture",
            required_repo="learntocloud/journal-starter",
        )
        request = _mock_request()
        current_user = AuthenticatedUser(user_id=1, github_username="user")

        with (
            patch(
                "learn_to_cloud.routes.htmx_routes.get_requirement_by_slug",
                return_value=requirement,
            ),
            patch(
                "learn_to_cloud.routes.htmx_routes.create_verification_job",
                new_callable=AsyncMock,
            ) as mock_create,
        ):
            result = await htmx_submit_verification(
                request,
                AsyncMock(),
                current_user,
                requirement_slug="deployment-architecture",
                architecture_description="   ",
            )

        assert isinstance(result, HTMLResponse)
        mock_create.assert_not_awaited()

    async def test_duplicate_submit_skips_durable_start(self):
        """When ``create_verification_job`` returns ``created=False``
        (concurrent submit raced into the same job row), the route does
        NOT call ``start_verification_orchestration`` — the original
        submit already kicked off Durable, and calling start_new again
        with the same instance id would error."""
        request = _mock_request()
        current_user = AuthenticatedUser(user_id=1, github_username="user")
        job = _mock_job()
        async_result = VerificationJobSubmission(
            job=cast(VerificationJob, job),
            created=False,
            requirement=_async_requirement(),
            github_username="user",
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
                "learn_to_cloud.routes.htmx_routes.create_verification_job",
                new_callable=AsyncMock,
                return_value=async_result,
            ),
            patch(
                "learn_to_cloud.routes.htmx_routes.start_verification_orchestration",
                new_callable=AsyncMock,
            ) as mock_start,
        ):
            result = await htmx_submit_verification(
                request,
                AsyncMock(),
                current_user,
                requirement_slug="req-1",
                submitted_value="https://github.com/user/repo",
            )

        assert isinstance(result, HTMLResponse)
        mock_start.assert_not_awaited()


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
            requirement_slug="req-1",
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
                "learn_to_cloud.routes.htmx_routes.get_requirement_by_slug",
                return_value=MagicMock(),
            ),
        ):
            result = await htmx_verification_job_status(
                request,
                AsyncMock(),
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
                "learn_to_cloud.routes.htmx_routes.get_verification_orchestration_status",
                new_callable=AsyncMock,
                return_value=DurableStatusResult(runtime_status="Completed"),
            ),
        ):
            result = await htmx_verification_job_status(
                request,
                AsyncMock(),
                token="signed-token",
                current_user=current_user,
            )

        assert isinstance(result, HTMLResponse)
        assert "location.reload()" in bytes(result.body).decode()

    async def test_failed_status_deletes_active_job_and_renders_error(
        self,
        _patch_templates,
    ):
        """Durable terminal failure deletes the row instead of marking
        a server-error status, then shows a retryable service error."""
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
                "learn_to_cloud.routes.htmx_routes.get_verification_orchestration_status",
                new_callable=AsyncMock,
                return_value=DurableStatusResult(runtime_status="Failed"),
            ),
            patch(
                "learn_to_cloud.routes.htmx_routes.VerificationJobRepository",
                autospec=True,
            ) as mock_repository_class,
            patch(
                "learn_to_cloud.routes.htmx_routes.get_requirement_by_slug",
                return_value=MagicMock(),
            ),
        ):
            mock_repository = mock_repository_class.return_value
            mock_repository.delete_active = AsyncMock(return_value=True)

            result = await htmx_verification_job_status(
                request,
                AsyncMock(),
                token="signed-token",
                current_user=current_user,
            )

        assert isinstance(result, HTMLResponse)
        mock_repository.delete_active.assert_awaited_once_with(job_id)
        mock_session.commit.assert_awaited_once()
        _, _, context = _patch_templates.TemplateResponse.call_args.args
        assert context["server_error"] is True
        assert context["server_error_retryable"] is False
        assert (
            context["server_error_message"]
            == "Verification failed because the verification service hit an internal "
            "error. Please try again in a few minutes. If it keeps failing, open an "
            "issue at https://github.com/learntocloud/learn-to-cloud-app/issues."
        )

    async def test_canceled_status_also_deletes_active_job(self):
        """``Canceled`` and ``Terminated`` are handled the same way as
        ``Failed`` — delete the row, let the user retry."""
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
                "learn_to_cloud.routes.htmx_routes.get_verification_orchestration_status",
                new_callable=AsyncMock,
                return_value=DurableStatusResult(runtime_status="Canceled"),
            ),
            patch(
                "learn_to_cloud.routes.htmx_routes.VerificationJobRepository",
                autospec=True,
            ) as mock_repository_class,
            patch(
                "learn_to_cloud.routes.htmx_routes.get_requirement_by_slug",
                return_value=MagicMock(),
            ),
        ):
            mock_repository = mock_repository_class.return_value
            mock_repository.delete_active = AsyncMock(return_value=True)

            result = await htmx_verification_job_status(
                request,
                AsyncMock(),
                token="signed-token",
                current_user=current_user,
            )

        assert isinstance(result, HTMLResponse)
        mock_repository.delete_active.assert_awaited_once_with(job_id)

    async def test_failed_status_delete_skipped_when_persist_won_race(self):
        """If ``delete_active`` returns False (persist linked a
        Submission first) the poller still responds with a reload — it
        just logs and moves on."""
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
                "learn_to_cloud.routes.htmx_routes.get_verification_orchestration_status",
                new_callable=AsyncMock,
                return_value=DurableStatusResult(runtime_status="Failed"),
            ),
            patch(
                "learn_to_cloud.routes.htmx_routes.VerificationJobRepository",
                autospec=True,
            ) as mock_repository_class,
        ):
            mock_repository = mock_repository_class.return_value
            mock_repository.delete_active = AsyncMock(return_value=False)

            result = await htmx_verification_job_status(
                request,
                AsyncMock(),
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
