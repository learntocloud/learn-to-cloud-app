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
from learn_to_cloud_shared.repositories.verification_attempt_repository import (
    VerificationAttemptRepository,
)
from learn_to_cloud_shared.requirements import get_requirement_by_slug
from learn_to_cloud_shared.schemas import (
    CareerReflectionRequirement,
    DeploymentArchitectureRequirement,
    SubmissionData,
)
from learn_to_cloud_shared.submission_derivation import (
    derive_submission_value,
    is_derivable,
)
from learn_to_cloud_shared.verification_attempt_executor import (
    terminalize_unstarted_verification_attempt,
    terminalize_verification_attempt,
)
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

if TYPE_CHECKING:
    from learn_to_cloud_shared.schemas import Topic

from learn_to_cloud.core.auth import AuthenticatedUser, CurrentUser, UserId
from learn_to_cloud.core.ratelimit import limiter
from learn_to_cloud.core.templates import templates
from learn_to_cloud.rendering.context import (
    build_progress_dict,
    build_requirement_card_context,
)
from learn_to_cloud.services.durable_verification_client import (
    DurableVerificationAuthError,
    DurableVerificationConfigError,
    DurableVerificationStartError,
    DurableVerificationStatusError,
    get_verification_attempt_status,
    start_verification_attempt_orchestration,
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
    VerificationAttemptSubmission,
    create_verification_attempt,
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
    current_user: AuthenticatedUser,
    token_data: VerificationStatusToken,
    token: str,
    *,
    delay_seconds: int,
) -> HTMLResponse:
    requirement = get_requirement_by_slug(token_data.requirement_slug)
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


async def _terminalize_failed_attempt(
    request: Request,
    token_data: VerificationStatusToken,
    status: str,
) -> bool:
    """Persist a terminal Durable failure."""
    session_maker = request.app.state.session_maker
    attempt_id = UUID(token_data.job_id)
    async with session_maker() as session:
        if await VerificationAttemptRepository(session).get_status(attempt_id) is None:
            return False

    cancelled = status in {"terminated", "canceled"}
    result = await terminalize_verification_attempt(
        attempt_id,
        outcome="cancelled" if cancelled else "server_error",
        error_code="cancelled" if cancelled else "server_error",
        validation_message=(
            "Verification was cancelled."
            if cancelled
            else "Verification failed before recording a result."
        ),
        terminal_source="poller",
        session_maker=session_maker,
    )
    if not result.won:
        logger.info(
            "verification.poller.finalize_skipped",
            extra={
                "attempt_id": str(attempt_id),
                "runtime_status": status,
                "outcome": result.state.outcome,
            },
        )
        return False
    logger.info(
        "verification.poller.attempt_terminalized",
        extra={
            "attempt_id": str(attempt_id),
            "runtime_status": status,
            "outcome": result.state.outcome,
            "cas_won": result.won,
        },
    )
    return True


async def _log_attempt_completion(
    request: Request,
    token_data: VerificationStatusToken,
    user_id: int,
    status: str,
) -> None:
    """Log the terminal state of an attempt the orchestration finalized.

    The poller is the API's only view of an attempt that Functions finished on
    its own, so without this a whole submission — success or ``server_error`` —
    leaves no server-side trace on the API (#700).
    """
    attempt_id = UUID(token_data.job_id)
    session_maker = request.app.state.session_maker
    try:
        async with session_maker() as session:
            state = await VerificationAttemptRepository(session).get_terminal_state(
                attempt_id
            )
    except SQLAlchemyError as exc:
        # The learner's result is already persisted and the page is about to
        # reload; a logging read must never turn that into a visible failure.
        logger.warning(
            "verification.attempt.completed_read_failed",
            extra={
                "user_id": user_id,
                "requirement_slug": token_data.requirement_slug,
                "attempt_id": str(attempt_id),
                "error_type": type(exc).__name__,
            },
        )
        return

    extra = {
        "user_id": user_id,
        "requirement_slug": token_data.requirement_slug,
        "attempt_id": str(attempt_id),
        "runtime_status": status,
        "outcome": state.outcome if state else None,
        "error_code": state.error_code if state else None,
        "terminal_source": state.terminal_source if state else None,
    }
    if state is None or state.outcome == "server_error":
        logger.warning("verification.attempt.observed", extra=extra)
    else:
        logger.info("verification.attempt.observed", extra=extra)


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
    except StepValidationError:
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
    except StepValidationError:
        response = HTMLResponse("")
        response.headers["HX-Refresh"] = "true"
        return response

    return await _render_step_toggle(request, user_id, topic, step, completed, db)


@router.post("/github/submit", response_class=HTMLResponse)
@limiter.limit("10/minute")
async def htmx_submit_verification(
    request: Request,
    current_user: CurrentUser,
    requirement_slug: Annotated[str, Form(max_length=100)],
    submitted_value: Annotated[str, Form(max_length=2048)] = "",
    answers: Annotated[list[str] | None, Form()] = None,
    architecture_description: Annotated[str, Form(max_length=20000)] = "",
) -> HTMLResponse:
    """Submit a hands-on verification.

    Every submission type runs through Durable Functions:
    :func:`create_verification_attempt` validates the request and creates a
    ``VerificationAttempt``; we start the versioned attempt orchestration and
    return a spinner card that polls for status.
    """
    user_id = current_user.user_id
    github_username = current_user.github_username

    requirement = get_requirement_by_slug(requirement_slug)

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

    # ── Create the unified verification attempt ─────────────────────────
    try:
        attempt_submission = await create_verification_attempt(
            session_maker=session_maker,
            user_id=user_id,
            requirement_slug=requirement_slug,
            submitted_value=derived_value,
            github_username=github_username,
        )
    except _USER_FACING_ERRORS as exc:
        return _render_card(error_banner=str(exc))
    except Exception as exc:
        logger.exception(
            "htmx.submit.unexpected_error",
            extra={
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

    logger.info(
        "verification.attempt.created",
        extra={
            "user_id": user_id,
            "requirement_slug": requirement_slug,
            "attempt_id": str(attempt_submission.attempt_id),
            "attempt_created": attempt_submission.created,
        },
    )

    return await _start_async_attempt_and_render(
        session_maker=session_maker,
        user_id=user_id,
        requirement_slug=requirement_slug,
        attempt_submission=attempt_submission,
        render_card=_render_card,
    )


async def _start_async_attempt_and_render(
    *,
    session_maker: async_sessionmaker[AsyncSession],
    user_id: int,
    requirement_slug: str,
    attempt_submission: VerificationAttemptSubmission,
    render_card: Callable[..., HTMLResponse],
) -> HTMLResponse:
    """Start the Durable attempt orchestration and render the spinner.

    Posts no body -- the attempt starter loads identity, the requirement
    snapshot, and the submitted value straight from ``verification_attempts``.

    On the rare concurrent-submit case (``created=False``) the original
    submit already kicked off Durable; we skip the start call and let
    the poller discover the existing instance via the shared id. If that
    original start never actually succeeded, the poller will see a 404
    from Durable and surface the error so the user can retry.

    On a Durable start-call failure that never reached Functions, terminalizes
    the just-created attempt so it remains in the outcome ledger without
    blocking the learner's retry.
    """
    try:
        if attempt_submission.created:
            await start_verification_attempt_orchestration(
                attempt_submission.attempt_id
            )

        status_token = create_verification_status_token(
            user_id=user_id,
            job_id=attempt_submission.attempt_id,
            instance_id=str(attempt_submission.attempt_id),
            requirement_slug=requirement_slug,
        )

        return render_card(
            processing=True,
            verification_status_token=status_token,
        )

    except (
        DurableVerificationConfigError,
        DurableVerificationAuthError,
        DurableVerificationStartError,
    ) as exc:
        logger.exception(
            "htmx.submit.durable_start_failed",
            extra={
                "requirement_slug": requirement_slug,
                "attempt_id": str(attempt_submission.attempt_id),
                "error_type": type(exc).__name__,
                "failure_kind": exc.failure_kind.value,
                "retryable": exc.retryable,
                "status_code": exc.status_code,
            },
        )
        await terminalize_unstarted_verification_attempt(
            attempt_submission.attempt_id,
            error_code=exc.error_code,
            validation_message="Verification could not be started.",
            terminal_source="api_start_failure",
            session_maker=session_maker,
        )
        if not exc.retryable:
            return render_card(
                server_error=True,
                server_error_message=_DURABLE_UNAVAILABLE_ERROR_MESSAGE,
                server_error_retryable=False,
            )
        return render_card(
            server_error=True,
            server_error_message=_DURABLE_START_ERROR_MESSAGE,
        )


@router.get("/verification/attempts/status", response_class=HTMLResponse)
async def htmx_verification_attempt_status(
    request: Request,
    token: Annotated[str, Query(max_length=4096)],
    current_user: CurrentUser,
) -> HTMLResponse:
    """Return a polling card or reload trigger based on Durable attempt status."""
    user_id = current_user.user_id
    try:
        token_data = load_verification_status_token(
            token,
            expected_user_id=user_id,
        )
    except VerificationStatusTokenError:
        return _status_error_response(
            "Verification status expired. Refresh the page to check for results.",
            status_code=400,
        )

    try:
        durable_status = await get_verification_attempt_status(token_data.instance_id)
    except (
        DurableVerificationAuthError,
        DurableVerificationConfigError,
        DurableVerificationStatusError,
    ) as exc:
        logger.warning(
            "verification.status.durable_read_failed",
            extra={
                "attempt_id": token_data.job_id,
                "error_type": type(exc).__name__,
                "failure_kind": exc.failure_kind.value,
                "retryable": exc.retryable,
                "status_code": exc.status_code,
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
            current_user,
            token_data,
            token,
            delay_seconds=_RUNNING_STATUS_DELAY_SECONDS,
        )

    if status in _DURABLE_FAILURE_STATUSES:
        terminalized = await _terminalize_failed_attempt(request, token_data, status)
        if not terminalized:
            return HTMLResponse(_reload_verification_html())

        requirement = get_requirement_by_slug(token_data.requirement_slug)
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
        await _log_attempt_completion(request, token_data, user_id, status)
        return HTMLResponse(_reload_verification_html())

    logger.warning(
        "verification.status.unexpected_durable_status",
        extra={
            "attempt_id": token_data.job_id,
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
        return HTMLResponse(
            '<p class="text-sm text-red-600">Account not found.</p>',
            status_code=404,
        )

    request.session.clear()
    response = HTMLResponse("")
    response.headers["HX-Redirect"] = "/"
    return response
