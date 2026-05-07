"""HTMX routes — return HTML fragments for partial page updates.

These routes handle interactive HTMX requests (step toggles, form
submissions, etc.) and return HTML partials instead of JSON.

Async verifications use Durable Functions + HTMX polling:
1. POST /htmx/github/submit — pre-validates and returns a spinner card
    immediately (~100ms)
2. Durable Functions runs verification and updates PostgreSQL job state
3. Browser polls an API proxy that checks Durable orchestration status
   without using PostgreSQL as the live status bus
"""

import logging
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Form, Query, Request
from fastapi.responses import HTMLResponse
from learn_to_cloud_shared.content_service import get_topic_by_id
from learn_to_cloud_shared.core.database import DbSession
from learn_to_cloud_shared.models import SubmissionType
from learn_to_cloud_shared.repositories.verification_job_repository import (
    VerificationJobRepository,
)
from learn_to_cloud_shared.schemas import SubmissionData
from learn_to_cloud_shared.verification.requirements import get_requirement_by_id
from learn_to_cloud_shared.verification.url_derivation import (
    derive_submission_value,
    is_derivable,
)

from learn_to_cloud.core.auth import AuthenticatedUser, CurrentUser, UserId
from learn_to_cloud.core.ratelimit import limiter
from learn_to_cloud.core.telemetry import add_span_event, record_span_exception
from learn_to_cloud.core.templates import templates
from learn_to_cloud.rendering.context import (
    build_progress_dict,
    build_requirement_card_context,
)
from learn_to_cloud.rendering.steps import build_step_data
from learn_to_cloud.services.durable_verification_client import (
    DurableVerificationConfigError,
    DurableVerificationStartError,
    DurableVerificationStatusError,
    get_verification_orchestration_status,
    start_verification_orchestration,
)
from learn_to_cloud.services.steps_service import (
    StepValidationError,
    complete_step,
    get_valid_completed_steps,
    parse_phase_id_from_topic_id,
    uncomplete_step,
)
from learn_to_cloud.services.submissions_service import (
    AlreadyValidatedError,
    DuplicatePrError,
    GitHubUsernameRequiredError,
    PriorPhaseNotCompleteError,
    RequirementNotFoundError,
    VerificationJobSubmission,
    create_verification_job,
)
from learn_to_cloud.services.users_service import (
    UserNotFoundError,
    delete_user_account,
    get_user_by_id,
)
from learn_to_cloud.services.verification_status_tokens import (
    VerificationStatusToken,
    VerificationStatusTokenError,
    create_verification_status_token,
    load_verification_status_token,
)

logger = logging.getLogger(__name__)

# Submission errors whose message is safe to show directly to the user.
_USER_FACING_ERRORS = (
    AlreadyValidatedError,
    DuplicatePrError,
    GitHubUsernameRequiredError,
    PriorPhaseNotCompleteError,
    RequirementNotFoundError,
)

_DURABLE_START_ERROR_MESSAGE = (
    "Verification could not be started. This attempt was not counted — "
    "please try again."
)

_ACTIVE_DURABLE_STATUSES = {"pending", "running", "continuedasnew"}
_TERMINAL_DURABLE_STATUSES = {"completed", "failed", "terminated", "canceled"}
_DURABLE_FAILURE_STATUSES = {"failed", "terminated", "canceled"}
_INITIAL_STATUS_DELAY_SECONDS = 2
_RUNNING_STATUS_DELAY_SECONDS = 5
_DURABLE_TERMINAL_FAILURE_MESSAGE = "Verification did not complete. Please try again."


router = APIRouter(prefix="/htmx", tags=["htmx"], include_in_schema=False)


def _reload_verification_html() -> str:
    return (
        "<div hx-trigger='load' "
        "hx-on::load='setTimeout(()=>location.reload(),100)'></div>"
    )


def _status_error_response(message: str, *, status_code: int = 400) -> HTMLResponse:
    return HTMLResponse(
        f"<div class='text-red-600 text-sm p-2'>{message}</div>",
        status_code=status_code,
    )


def _render_processing_card(
    request: Request,
    current_user: AuthenticatedUser,
    token_data: VerificationStatusToken,
    token: str,
    *,
    delay_seconds: int,
) -> HTMLResponse:
    requirement = get_requirement_by_id(token_data.requirement_id)
    if requirement is None:
        return HTMLResponse(_reload_verification_html())

    return templates.TemplateResponse(
        request,
        "partials/requirement_card.html",
        build_requirement_card_context(
            requirement=requirement,
            github_username=current_user.github_username,
            processing=True,
            verification_status_token=token,
            verification_status_delay_seconds=delay_seconds,
        ),
    )


async def _mark_durable_terminal_failure(
    request: Request,
    token_data: VerificationStatusToken,
    status: str,
) -> None:
    session_maker = request.app.state.session_maker
    async with session_maker() as session:
        repository = VerificationJobRepository(session)
        job_id = UUID(token_data.job_id)
        error_code = f"durable_{status}"
        if status == "canceled":
            await repository.mark_cancelled(
                job_id,
                error_code=error_code,
                error_message=_DURABLE_TERMINAL_FAILURE_MESSAGE,
            )
        else:
            await repository.mark_server_error(
                job_id,
                error_code=error_code,
                error_message=_DURABLE_TERMINAL_FAILURE_MESSAGE,
            )
        await session.commit()


async def _render_step_toggle(
    request: Request,
    db: DbSession,
    user_id: int,
    topic_id: str,
    step_id: str,
    phase_id: int,
) -> HTMLResponse:
    """Shared rendering for step complete/uncomplete HTMX responses.

    Looks up the step content and returns the combined step + progress
    HTML partials.
    """
    topic = get_topic_by_id(topic_id)
    step = None
    if topic:
        for s in topic.learning_steps:
            if s.id == step_id:
                step = s
                break

    if step is None:
        add_span_event(
            "step_not_found",
            {"user_id": user_id, "topic_id": topic_id, "step_id": step_id},
        )
        return HTMLResponse("")

    assert topic is not None  # guaranteed: topic=None → step=None → early return
    step_data = build_step_data(step)
    user = await get_user_by_id(db, user_id)
    completed_steps = await get_valid_completed_steps(db, user_id, topic)

    total_steps = len(topic.learning_steps)
    progress = build_progress_dict(len(completed_steps), total_steps)

    step_html = templates.get_template("partials/topic_step.html").render(
        request=request,
        step=step_data,
        topic_id=topic_id,
        phase_id=phase_id,
        completed_steps=completed_steps,
        user=user,
    )
    progress_html = templates.get_template("partials/topic_progress.html").render(
        progress=progress
    )

    return HTMLResponse(step_html + progress_html)


@router.post("/steps/complete", response_class=HTMLResponse)
async def htmx_complete_step(
    request: Request,
    db: DbSession,
    user_id: UserId,
    topic_id: Annotated[str, Form()],
    step_id: Annotated[str, Form()],
    phase_id: Annotated[int, Form()],
) -> HTMLResponse:
    """Complete a step and return the updated step partial."""
    try:
        await complete_step(db, user_id, topic_id, step_id)
    except StepValidationError as e:
        add_span_event(
            "step_complete_invalid",
            {
                "user_id": user_id,
                "topic_id": topic_id,
                "step_id": step_id,
                "error": str(e),
            },
        )
        # Step ID doesn't exist in current content (stale cached page).
        # Force a full page reload so the user gets the current steps.
        response = HTMLResponse("")
        response.headers["HX-Refresh"] = "true"
        return response
    return await _render_step_toggle(request, db, user_id, topic_id, step_id, phase_id)


@router.delete("/steps/{topic_id}/{step_id}", response_class=HTMLResponse)
async def htmx_uncomplete_step(
    request: Request,
    topic_id: str,
    step_id: str,
    db: DbSession,
    user_id: UserId,
) -> HTMLResponse:
    """Uncomplete a step and return the updated step partial."""
    try:
        await uncomplete_step(db, user_id, topic_id, step_id)
    except StepValidationError as e:
        add_span_event(
            "step_uncomplete_invalid",
            {
                "user_id": user_id,
                "topic_id": topic_id,
                "step_id": step_id,
                "error": str(e),
            },
        )
        response = HTMLResponse("")
        response.headers["HX-Refresh"] = "true"
        return response

    phase_id = parse_phase_id_from_topic_id(topic_id) or 0

    return await _render_step_toggle(request, db, user_id, topic_id, step_id, phase_id)


@router.post("/github/submit", response_class=HTMLResponse)
@limiter.limit("10/minute")
async def htmx_submit_verification(
    request: Request,
    current_user: CurrentUser,
    requirement_id: Annotated[str, Form(max_length=100)],
    submitted_value: Annotated[str, Form(max_length=2048)] = "",
    pr_number: Annotated[str, Form(max_length=16)] = "",
) -> HTMLResponse:
    """Submit a hands-on verification and start its Durable orchestration."""
    user_id = current_user.user_id
    github_username = current_user.github_username

    requirement = get_requirement_by_id(requirement_id)

    session_maker = request.app.state.session_maker

    def _render_card(
        submission: SubmissionData | None = None,
        *,
        feedback_tasks: list | None = None,
        feedback_passed: int = 0,
        server_error: bool = False,
        server_error_message: str | None = None,
        error_banner: str | None = None,
        processing: bool = False,
        verification_status_token: str | None = None,
        verification_status_delay_seconds: int = _INITIAL_STATUS_DELAY_SECONDS,
    ) -> HTMLResponse:
        """Render the requirement card partial with consistent context."""
        return templates.TemplateResponse(
            request,
            "partials/requirement_card.html",
            build_requirement_card_context(
                requirement=requirement,
                github_username=github_username,
                submission=submission,
                feedback_tasks=feedback_tasks or [],
                feedback_passed=feedback_passed,
                server_error=server_error,
                server_error_message=server_error_message,
                error_banner=error_banner,
                processing=processing,
                verification_status_token=verification_status_token,
                verification_status_delay_seconds=verification_status_delay_seconds,
            ),
        )

    # ── Derive the canonical submission value ──────────────────────────
    if requirement is not None:
        try:
            if requirement.submission_type == SubmissionType.PR_REVIEW:
                user_input: str | None = pr_number
            elif is_derivable(requirement.submission_type):
                user_input = None
            else:
                user_input = submitted_value
                if not user_input or not user_input.strip():
                    return _render_card(
                        error_banner="Please enter a value before submitting."
                    )
            if github_username is None and not is_derivable(
                requirement.submission_type
            ):
                derived_value = user_input or ""
            else:
                derived_value = derive_submission_value(
                    requirement=requirement,
                    github_username=github_username or "",
                    user_input=user_input,
                )
        except ValueError as ve:
            return _render_card(error_banner=str(ve))
    else:
        derived_value = submitted_value

    # ── Persist job, then start Durable orchestration ──────────────────
    job_submission: VerificationJobSubmission | None = None
    try:
        job_submission = await create_verification_job(
            session_maker=session_maker,
            user_id=user_id,
            requirement_id=requirement_id,
            submitted_value=derived_value,
            github_username=github_username,
        )

        existing_instance_id = job_submission.job.orchestration_instance_id
        if job_submission.created or existing_instance_id is None:
            start_result = await start_verification_orchestration(job_submission.job.id)
            instance_id = start_result.instance_id
            async with session_maker() as write_session:
                await VerificationJobRepository(write_session).mark_starting(
                    job_submission.job.id,
                    start_result.instance_id,
                )
                await write_session.commit()
        else:
            instance_id = existing_instance_id

        status_token = create_verification_status_token(
            user_id=user_id,
            job_id=job_submission.job.id,
            instance_id=instance_id,
            requirement_id=requirement_id,
        )

        return _render_card(
            processing=True,
            verification_status_token=status_token,
        )

    except _USER_FACING_ERRORS as exc:
        return _render_card(error_banner=str(exc))
    except (
        DurableVerificationConfigError,
        DurableVerificationStartError,
    ) as exc:
        record_span_exception(exc)
        logger.warning(
            "htmx.submit.durable_start_failed",
            extra={
                "user_id": user_id,
                "requirement_id": requirement_id,
                "error_type": type(exc).__name__,
            },
        )
        if job_submission is not None:
            async with session_maker() as write_session:
                await VerificationJobRepository(write_session).mark_server_error(
                    job_submission.job.id,
                    error_code="durable_start_failed",
                    error_message=_DURABLE_START_ERROR_MESSAGE,
                )
                await write_session.commit()
        return _render_card(
            server_error=True,
            server_error_message=_DURABLE_START_ERROR_MESSAGE,
        )
    except Exception as exc:
        record_span_exception(exc)
        logger.exception(
            "htmx.submit.unexpected_error",
            extra={
                "user_id": user_id,
                "requirement_id": requirement_id,
                "error_type": type(exc).__name__,
            },
        )
        return _render_card(
            server_error=True,
            server_error_message=(
                "An unexpected error occurred during verification. "
                "This attempt was not counted — please try again."
            ),
        )


@router.get("/verification/jobs/status", response_class=HTMLResponse)
async def htmx_verification_job_status(
    request: Request,
    token: Annotated[str, Query(max_length=4096)],
    current_user: CurrentUser,
) -> HTMLResponse:
    """Return a polling card or reload trigger based on Durable job status."""
    user_id = current_user.user_id
    try:
        token_data = load_verification_status_token(
            token,
            expected_user_id=user_id,
        )
    except VerificationStatusTokenError as exc:
        add_span_event(
            "verification_status_token_invalid",
            {"user_id": user_id, "error": str(exc)},
        )
        return _status_error_response(
            "Verification status expired. Refresh the page to check for results.",
            status_code=400,
        )

    try:
        durable_status = await get_verification_orchestration_status(
            token_data.instance_id
        )
    except (DurableVerificationConfigError, DurableVerificationStatusError) as exc:
        record_span_exception(
            exc,
            {
                "user.id": user_id,
                "verification.job_id": str(token_data.job_id),
            },
        )
        logger.warning(
            "verification.status.durable_read_failed",
            extra={
                "user_id": user_id,
                "job_id": token_data.job_id,
                "error_type": type(exc).__name__,
            },
        )
        return _status_error_response(
            "Unable to load verification status. "
            "Refresh the page to check for results.",
            status_code=502,
        )

    status = durable_status.runtime_status.lower()
    if status in _ACTIVE_DURABLE_STATUSES:
        return _render_processing_card(
            request,
            current_user,
            token_data,
            token,
            delay_seconds=_RUNNING_STATUS_DELAY_SECONDS,
        )

    if status in _DURABLE_FAILURE_STATUSES:
        await _mark_durable_terminal_failure(request, token_data, status)
        return HTMLResponse(_reload_verification_html())

    if status in _TERMINAL_DURABLE_STATUSES:
        return HTMLResponse(_reload_verification_html())

    logger.warning(
        "verification.status.unexpected_durable_status",
        extra={
            "user_id": user_id,
            "job_id": token_data.job_id,
            "runtime_status": durable_status.runtime_status,
        },
    )
    return _status_error_response(
        "Verification is in an unexpected state. "
        "Refresh the page to check for results.",
        status_code=409,
    )


@router.delete("/account", response_class=HTMLResponse)
@limiter.limit("3/hour")
async def htmx_delete_account(
    request: Request,
    db: DbSession,
    user_id: UserId,
) -> HTMLResponse:
    """Delete the current user's account and redirect to home via HTMX."""
    try:
        await delete_user_account(db, user_id)
    except UserNotFoundError:
        add_span_event("account_delete_not_found", {"user_id": user_id})
        return HTMLResponse(
            '<p class="text-sm text-red-600">Account not found.</p>',
            status_code=404,
        )

    request.session.clear()
    response = HTMLResponse("")
    response.headers["HX-Redirect"] = "/"
    return response
