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
from collections.abc import Callable
from typing import TYPE_CHECKING, Annotated
from uuid import UUID

from fastapi import APIRouter, Form, Query, Request
from fastapi.responses import HTMLResponse
from learn_to_cloud_shared.core.database import DbSession
from learn_to_cloud_shared.repositories.verification_job_repository import (
    VerificationJobRepository,
)
from learn_to_cloud_shared.schemas import (
    CareerReflectionRequirement,
    DeploymentArchitectureRequirement,
    SubmissionData,
)
from learn_to_cloud_shared.submission_values import submission_value_from_columns
from learn_to_cloud_shared.verification.execution import (
    SubmissionAlreadyInFlightError,
)
from learn_to_cloud_shared.verification.requirements import get_requirement_by_slug
from learn_to_cloud_shared.verification.url_derivation import (
    derive_submission_value,
    is_derivable,
)
from learn_to_cloud_shared.verification_job_executor import PreparedVerificationJob
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

if TYPE_CHECKING:
    from learn_to_cloud_shared.schemas import Topic

from learn_to_cloud.core.auth import AuthenticatedUser, CurrentUser, UserId
from learn_to_cloud.core.ratelimit import limiter
from learn_to_cloud.core.telemetry import add_span_event, record_span_exception
from learn_to_cloud.core.templates import templates
from learn_to_cloud.rendering.context import (
    build_progress_dict,
    build_requirement_card_context,
)
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
    uncomplete_step,
)
from learn_to_cloud.services.submissions_service import (
    AlreadyValidatedError,
    InvalidSubmittedValueError,
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
    InvalidSubmittedValueError,
    PriorPhaseNotCompleteError,
    RequirementNotFoundError,
    SubmissionAlreadyInFlightError,
)

_DURABLE_START_ERROR_MESSAGE = (
    "Verification could not be started. This attempt was not counted, please try again."
)
_DURABLE_UNAVAILABLE_ERROR_MESSAGE = (
    "Verification is temporarily unavailable because of a problem on our side, "
    "not something you did. Retrying won't fix it. Please report it by opening "
    "an issue at https://github.com/learntocloud/learn-to-cloud-app/issues."
)
_DURABLE_TERMINAL_ERROR_MESSAGE = (
    "Verification failed because the verification service hit an internal error. "
    "Please try again in a few minutes. If it keeps failing, open an issue at "
    "https://github.com/learntocloud/learn-to-cloud-app/issues."
)

_ACTIVE_DURABLE_STATUSES = {"pending", "running", "continuedasnew"}
_TERMINAL_DURABLE_STATUSES = {"completed", "failed", "terminated", "canceled"}
_DURABLE_FAILURE_STATUSES = {"failed", "terminated", "canceled"}
_INITIAL_STATUS_DELAY_SECONDS = 2
_RUNNING_STATUS_DELAY_SECONDS = 5

# Per-answer cap for career reflection submissions. Three answers plus their
# question headers must stay under the 20,000-character text value limit.
_MAX_REFLECTION_ANSWER_LENGTH = 6000


def _combine_reflection_answers(
    requirement: CareerReflectionRequirement,
    answers: list[str],
) -> str:
    """Validate the per-question reflection answers and combine them into text.

    Each answer is matched to its question, checked against the configured
    minimum and maximum length, and joined under a Markdown header so the LLM
    grader can tell which answer belongs to which prompt.

    Raises:
        ValueError: With a learner-facing message if the answers are missing,
            too short, or too long.
    """
    questions = list(requirement.type_config.questions)
    min_length = requirement.type_config.min_answer_length

    cleaned = [answer.strip() for answer in answers]
    if len(cleaned) != len(questions):
        raise ValueError("Please answer all of the reflection questions.")

    sections: list[str] = []
    for question, answer in zip(questions, cleaned, strict=True):
        if len(answer) < min_length:
            raise ValueError(
                f"Each answer needs at least {min_length} characters. "
                "Add more detail and try again."
            )
        if len(answer) > _MAX_REFLECTION_ANSWER_LENGTH:
            raise ValueError(
                "One of your answers is too long. Please keep each answer "
                f"under {_MAX_REFLECTION_ANSWER_LENGTH} characters."
            )
        sections.append(f"## {question.prompt}\n\n{answer}")

    return "\n\n".join(sections)


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


async def _render_processing_card(
    request: Request,
    db: DbSession,
    current_user: AuthenticatedUser,
    token_data: VerificationStatusToken,
    token: str,
    *,
    delay_seconds: int,
) -> HTMLResponse:
    requirement = await get_requirement_by_slug(db, token_data.requirement_slug)
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


async def _delete_terminal_job(
    request: Request,
    token_data: VerificationStatusToken,
    status: str,
) -> bool:
    """Drop the verification_jobs row after Durable reaches terminal failure.

    Replaces the older ``mark_server_error`` / ``mark_cancelled`` writes:
    the user-facing failure message comes from Durable's runtime status
    in the poller, not from a Postgres re-read, so we don't need to copy
    Durable's terminal state back into Postgres. Deleting frees the
    partial unique index so the user can retry.

    The delete is guarded — if the persist activity won a race and
    attached a Submission first, ``delete_active`` returns False and we
    leave the row alone.
    """
    session_maker = request.app.state.session_maker
    async with session_maker() as session:
        repository = VerificationJobRepository(session)
        job_id = UUID(token_data.job_id)
        deleted = await repository.delete_active(job_id)
        await session.commit()
    if not deleted:
        logger.info(
            "verification.poller.delete_skipped",
            extra={"job_id": str(job_id), "runtime_status": status},
        )
    return deleted


async def _render_step_toggle(
    request: Request,
    user_id: int,
    topic: "Topic",
    step,
    completed_step_uuids: set[UUID],
    db: DbSession,
) -> HTMLResponse:
    """Shared rendering for step complete/uncomplete HTMX responses."""
    user = await get_user_by_id(db, user_id)

    total_steps = len(topic.learning_steps)
    progress = build_progress_dict(len(completed_step_uuids), total_steps)

    step_html = templates.get_template("partials/topic_step.html").render(
        request=request,
        step=step,
        completed_steps=completed_step_uuids,
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
    step_uuid: Annotated[UUID, Form()],
) -> HTMLResponse:
    """Complete a step and return the updated step partial."""
    try:
        _, topic, completed = await complete_step(db, user_id, step_uuid)
    except StepValidationError as e:
        add_span_event(
            "step_complete_invalid",
            {
                "user_id": user_id,
                "step_uuid": str(step_uuid),
                "error": str(e),
            },
        )
        # Step UUID doesn't exist in current content (stale cached page).
        # Force a full page reload so the user gets the current steps.
        response = HTMLResponse("")
        response.headers["HX-Refresh"] = "true"
        return response

    step = next(s for s in topic.learning_steps if s.uuid == step_uuid)
    return await _render_step_toggle(request, user_id, topic, step, completed, db)


@router.delete("/steps/{step_uuid}", response_class=HTMLResponse)
async def htmx_uncomplete_step(
    request: Request,
    step_uuid: UUID,
    db: DbSession,
    user_id: UserId,
) -> HTMLResponse:
    """Uncomplete a step and return the updated step partial."""
    try:
        _, topic, step, completed = await uncomplete_step(db, user_id, step_uuid)
    except StepValidationError as e:
        add_span_event(
            "step_uncomplete_invalid",
            {
                "user_id": user_id,
                "step_uuid": str(step_uuid),
                "error": str(e),
            },
        )
        response = HTMLResponse("")
        response.headers["HX-Refresh"] = "true"
        return response

    return await _render_step_toggle(request, user_id, topic, step, completed, db)


@router.post("/github/submit", response_class=HTMLResponse)
@limiter.limit("10/minute")
async def htmx_submit_verification(
    request: Request,
    db: DbSession,
    current_user: CurrentUser,
    requirement_slug: Annotated[str, Form(max_length=100)],
    submitted_value: Annotated[str, Form(max_length=2048)] = "",
    answers: Annotated[list[str] | None, Form()] = None,
    architecture_description: Annotated[str, Form(max_length=20000)] = "",
) -> HTMLResponse:
    """Submit a hands-on verification.

    Every submission type runs through Durable Functions:
    :func:`create_verification_job` validates the request and creates a
    ``VerificationJob``; we start the Durable orchestration and return a
    spinner card that polls for status.
    """
    user_id = current_user.user_id
    github_username = current_user.github_username

    requirement = await get_requirement_by_slug(db, requirement_slug)

    session_maker = request.app.state.session_maker

    def _render_card(
        submission: SubmissionData | None = None,
        *,
        feedback_tasks: list | None = None,
        feedback_passed: int = 0,
        server_error: bool = False,
        server_error_message: str | None = None,
        server_error_retryable: bool = True,
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
                server_error_retryable=server_error_retryable,
                error_banner=error_banner,
                processing=processing,
                verification_status_token=verification_status_token,
                verification_status_delay_seconds=verification_status_delay_seconds,
            ),
        )

    # ── Derive the canonical submission value ──────────────────────────
    if requirement is not None:
        try:
            if isinstance(requirement, CareerReflectionRequirement):
                user_input = _combine_reflection_answers(requirement, answers or [])
            elif isinstance(requirement, DeploymentArchitectureRequirement):
                user_input = architecture_description.strip()
                if not user_input:
                    return _render_card(
                        error_banner="Please write a description before submitting."
                    )
            elif is_derivable(requirement.submission_type):
                user_input = None
            else:
                user_input = submitted_value
                if not user_input or not user_input.strip():
                    return _render_card(
                        error_banner="Please enter a value before submitting."
                    )
            derived_value = derive_submission_value(
                requirement=requirement,
                github_username=github_username,
                user_input=user_input,
            )
        except ValueError as ve:
            return _render_card(error_banner=str(ve))
    else:
        derived_value = submitted_value

    # ── Create the Durable verification job ────────────────────────────
    try:
        job_submission = await create_verification_job(
            session_maker=session_maker,
            user_id=user_id,
            requirement_slug=requirement_slug,
            submitted_value=derived_value,
            github_username=github_username,
        )
    except _USER_FACING_ERRORS as exc:
        return _render_card(error_banner=str(exc))
    except Exception as exc:
        record_span_exception(exc)
        logger.exception(
            "htmx.submit.unexpected_error",
            extra={
                "user_id": user_id,
                "requirement_slug": requirement_slug,
                "error_type": type(exc).__name__,
            },
        )
        return _render_card(
            server_error=True,
            server_error_message=(
                "An unexpected error occurred during verification. "
                "This attempt was not counted, please try again."
            ),
        )

    return await _start_async_job_and_render(
        session_maker=session_maker,
        user_id=user_id,
        requirement_slug=requirement_slug,
        job_submission=job_submission,
        render_card=_render_card,
    )


async def _start_async_job_and_render(
    *,
    session_maker: async_sessionmaker[AsyncSession],
    user_id: int,
    requirement_slug: str,
    job_submission: VerificationJobSubmission,
    render_card: Callable[..., HTMLResponse],
) -> HTMLResponse:
    """Start a Durable orchestration for an async job and render the spinner.

    Builds the full :class:`PreparedVerificationJob` payload from the
    validated requirement + github_username carried on
    ``job_submission`` and posts it to the Functions starter. Functions
    validates the immutable fields against the ``verification_jobs``
    row before starting; the payload is trusted for the requirement
    definition + username snapshot so Functions never needs to read
    curriculum or users tables.

    On the rare concurrent-submit case (``created=False``) the original
    submit already kicked off Durable; we skip the start call and let
    the poller discover the existing instance via ``job.id``. If that
    original start never actually succeeded, the poller will see a 404
    from Durable and surface the error so the user can retry.

    On Durable start failure deletes the just-created row so the
    partial unique index doesn't block the user's retry.
    """
    try:
        if job_submission.created:
            prepared = PreparedVerificationJob(
                id=job_submission.job.id,
                user_id=user_id,
                github_username=job_submission.github_username,
                requirement=job_submission.requirement,
                submitted_value=submission_value_from_columns(job_submission.job),
            )
            await start_verification_orchestration(prepared)

        status_token = create_verification_status_token(
            user_id=user_id,
            job_id=job_submission.job.id,
            instance_id=str(job_submission.job.id),
            requirement_slug=requirement_slug,
        )

        return render_card(
            processing=True,
            verification_status_token=status_token,
        )

    except (
        DurableVerificationConfigError,
        DurableVerificationStartError,
    ) as exc:
        record_span_exception(exc)
        logger.exception(
            "htmx.submit.durable_start_failed",
            extra={
                "user_id": user_id,
                "requirement_slug": requirement_slug,
                "error_type": type(exc).__name__,
                "error_message": str(exc),
                "error_cause": (
                    f"{type(exc.__cause__).__name__}: {exc.__cause__}"
                    if exc.__cause__ is not None
                    else None
                ),
            },
        )
        # Delete the just-created row so the partial unique index doesn't
        # block the user's retry. Durable owns terminal-state messaging
        # now; we just need to free the in-flight slot.
        async with session_maker() as write_session:
            await VerificationJobRepository(write_session).delete_active(
                job_submission.job.id,
            )
            await write_session.commit()
        # A config error means the verification service is misconfigured on our
        # side, so retrying will never help. A start error is usually a
        # transient hiccup in the Functions app, so retrying is worth it.
        if isinstance(exc, DurableVerificationConfigError):
            return render_card(
                server_error=True,
                server_error_message=_DURABLE_UNAVAILABLE_ERROR_MESSAGE,
                server_error_retryable=False,
            )
        return render_card(
            server_error=True,
            server_error_message=_DURABLE_START_ERROR_MESSAGE,
        )


@router.get("/verification/jobs/status", response_class=HTMLResponse)
async def htmx_verification_job_status(
    request: Request,
    db: DbSession,
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
        return await _render_processing_card(
            request,
            db,
            current_user,
            token_data,
            token,
            delay_seconds=_RUNNING_STATUS_DELAY_SECONDS,
        )

    if status in _DURABLE_FAILURE_STATUSES:
        deleted = await _delete_terminal_job(request, token_data, status)
        if not deleted:
            return HTMLResponse(_reload_verification_html())

        requirement = await get_requirement_by_slug(db, token_data.requirement_slug)
        if requirement is None:
            return HTMLResponse(_reload_verification_html())

        return templates.TemplateResponse(
            request,
            "partials/requirement_card.html",
            build_requirement_card_context(
                requirement=requirement,
                github_username=current_user.github_username,
                server_error=True,
                server_error_message=_DURABLE_TERMINAL_ERROR_MESSAGE,
                server_error_retryable=False,
            ),
        )

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
