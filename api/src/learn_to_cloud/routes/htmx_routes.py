"""HTMX routes — return HTML fragments for partial page updates.

These routes handle interactive HTMX requests (step toggles, form
submissions, etc.) and return HTML partials instead of JSON.

Async verifications use Durable Functions + HTMX polling:
1. A shape-specific verification POST pre-validates and returns a spinner card
    immediately (~100ms)
2. Durable Functions runs verification and updates PostgreSQL job state
3. Browser polls an API proxy that checks Durable orchestration status
   without using PostgreSQL as the live status bus
"""

import logging
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Form, Path, Query, Request
from fastapi.responses import HTMLResponse
from learn_to_cloud_shared.core.database import DbSession
from learn_to_cloud_shared.requirements import get_requirement_by_slug
from learn_to_cloud_shared.schemas import (
    CareerReflectionRequirement,
    HandsOnRequirement,
    PlaceholderConfig,
)
from learn_to_cloud_shared.submission_derivation import derive_submission_value
from learn_to_cloud_shared.submission_values import (
    SubmittedValue,
    submitted_value_from_raw,
)
from pydantic import BaseModel, ValidationError

from learn_to_cloud.core.auth import AuthenticatedUser, CurrentUser, UserId
from learn_to_cloud.core.ratelimit import limiter
from learn_to_cloud.rendering.htmx_responses import (
    reload_page_response,
    render_input_error,
    render_processing,
    render_step_toggle,
    render_unavailable,
    status_error_response,
)
from learn_to_cloud.services.durable_verification_client import (
    DurableVerificationAuthError,
    DurableVerificationConfigError,
    DurableVerificationStatusError,
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
)
from learn_to_cloud.services.users_service import (
    UserNotFoundError,
    delete_user_account,
)
from learn_to_cloud.services.verification_attempt_service import (
    VerificationPollKind,
    poll_verification_attempt,
    submit_verification_attempt,
)
from learn_to_cloud.services.verification_status_tokens import (
    VerificationStatusTokenError,
    load_verification_status_token,
)
from learn_to_cloud.verification_forms import (
    DerivedVerificationForm,
    ReflectionVerificationForm,
    ValueVerificationForm,
    VerificationInputShape,
    combine_reflection_answers,
    input_shape_for_submission_type,
)

logger = logging.getLogger(__name__)

# Submission errors whose message is safe to show directly to the user.
_USER_FACING_ERRORS = (
    AlreadyValidatedError,
    InvalidSubmittedValueError,
    PriorPhaseNotCompleteError,
    RequirementNotFoundError,
)

_INITIAL_STATUS_DELAY_SECONDS = 2
_RUNNING_STATUS_DELAY_SECONDS = 5
_VERIFICATION_SUBMIT_RATE_LIMIT_SCOPE = "verification-submit"
_INVALID_FORM_MESSAGE = (
    "This verification form is out of date or invalid. Refresh the page and try again."
)

router = APIRouter(prefix="/htmx", tags=["htmx"], include_in_schema=False)


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
    return await render_step_toggle(request, user_id, topic, step, completed, db)


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

    return await render_step_toggle(request, user_id, topic, step, completed, db)


async def _parse_verification_form[FormModel: BaseModel](
    request: Request,
    model_type: type[FormModel],
    *,
    list_fields: frozenset[str] = frozenset(),
) -> FormModel | None:
    """Parse one known form shape without exposing JSON validation errors."""
    form = await request.form()
    payload: dict[str, object] = {}
    for key in form:
        values = form.getlist(key)
        if key in list_fields:
            payload[key] = values
        elif len(values) == 1:
            payload[key] = values[0]
        else:
            return None
    try:
        return model_type.model_validate(payload)
    except ValidationError:
        return None


def _resolve_requirement(
    requirement_slug: str,
    expected_shape: VerificationInputShape,
) -> tuple[HandsOnRequirement | None, bool]:
    """Resolve a requirement and report whether its HTTP shape matches."""
    requirement = get_requirement_by_slug(requirement_slug)
    if requirement is None:
        return None, False
    matches = (
        input_shape_for_submission_type(requirement.submission_type) == expected_shape
    )
    return requirement, matches


async def _submit_canonical_verification(
    request: Request,
    current_user: AuthenticatedUser,
    requirement: HandsOnRequirement,
    submitted_value: SubmittedValue,
) -> HTMLResponse:
    """Create and start an attempt from a canonical submission value."""
    requirement_slug = requirement.slug
    try:
        result = await submit_verification_attempt(
            session_maker=request.app.state.session_maker,
            user_id=current_user.user_id,
            github_username=current_user.github_username,
            requirement_slug=requirement_slug,
            submitted_value=submitted_value,
        )
    except _USER_FACING_ERRORS as exc:
        return render_input_error(request, current_user, requirement, str(exc))
    except Exception as exc:
        logger.exception(
            "htmx.submit.unexpected_error",
            extra={
                "requirement_slug": requirement_slug,
                "error_type": type(exc).__name__,
            },
        )
        return render_unavailable(
            request,
            current_user,
            requirement,
            (
                "An unexpected error occurred during verification. "
                "This attempt was not counted, please try again."
            ),
        )

    if result.status_token is not None:
        return render_processing(
            request,
            requirement,
            result.status_token,
            delay_seconds=_INITIAL_STATUS_DELAY_SECONDS,
        )
    return render_unavailable(
        request,
        current_user,
        requirement,
        result.unavailable_message
        or "Verification could not be started. Please try again.",
    )


def _invalid_form_response(
    request: Request,
    current_user: AuthenticatedUser,
    requirement: HandsOnRequirement,
    message: str = _INVALID_FORM_MESSAGE,
) -> HTMLResponse:
    return render_input_error(request, current_user, requirement, message)


@router.post(
    "/verifications/{requirement_slug}/submit/derived",
    response_class=HTMLResponse,
)
@limiter.shared_limit("10/minute", scope=_VERIFICATION_SUBMIT_RATE_LIMIT_SCOPE)
async def htmx_submit_derived_verification(
    request: Request,
    current_user: CurrentUser,
    requirement_slug: Annotated[str, Path(max_length=100)],
) -> HTMLResponse:
    """Submit a verification whose canonical value is server-derived."""
    requirement, matches = _resolve_requirement(
        requirement_slug,
        VerificationInputShape.DERIVED,
    )
    if requirement is None:
        return reload_page_response()
    if not matches:
        return _invalid_form_response(request, current_user, requirement)
    form = await _parse_verification_form(request, DerivedVerificationForm)
    if form is None:
        return _invalid_form_response(request, current_user, requirement)
    try:
        submitted_value = derive_submission_value(
            requirement=requirement,
            github_username=current_user.github_username,
        )
    except ValueError as exc:
        return _invalid_form_response(request, current_user, requirement, str(exc))
    return await _submit_canonical_verification(
        request,
        current_user,
        requirement,
        submitted_value,
    )


@router.post(
    "/verifications/{requirement_slug}/submit/value",
    response_class=HTMLResponse,
)
@limiter.shared_limit("10/minute", scope=_VERIFICATION_SUBMIT_RATE_LIMIT_SCOPE)
async def htmx_submit_value_verification(
    request: Request,
    current_user: CurrentUser,
    requirement_slug: Annotated[str, Path(max_length=100)],
) -> HTMLResponse:
    """Submit a verification with one learner-provided value."""
    requirement, matches = _resolve_requirement(
        requirement_slug,
        VerificationInputShape.VALUE,
    )
    if requirement is None:
        return reload_page_response()
    if not matches or not isinstance(requirement.type_config, PlaceholderConfig):
        return _invalid_form_response(request, current_user, requirement)
    form = await _parse_verification_form(request, ValueVerificationForm)
    if form is None:
        return _invalid_form_response(request, current_user, requirement)
    submitted_value = form.submitted_value.strip()
    if not submitted_value:
        return _invalid_form_response(
            request,
            current_user,
            requirement,
            "Please enter a value before submitting.",
        )
    min_length = requirement.type_config.min_length
    max_length = requirement.type_config.max_length
    if len(submitted_value) < min_length:
        return _invalid_form_response(
            request,
            current_user,
            requirement,
            f"Please enter at least {min_length} characters before submitting.",
        )
    if len(submitted_value) > max_length:
        return _invalid_form_response(
            request,
            current_user,
            requirement,
            f"Please enter no more than {max_length} characters.",
        )
    try:
        typed_value = submitted_value_from_raw(requirement, submitted_value)
    except ValueError as exc:
        return _invalid_form_response(request, current_user, requirement, str(exc))
    return await _submit_canonical_verification(
        request,
        current_user,
        requirement,
        typed_value,
    )


@router.post(
    "/verifications/{requirement_slug}/submit/reflection",
    response_class=HTMLResponse,
)
@limiter.shared_limit("10/minute", scope=_VERIFICATION_SUBMIT_RATE_LIMIT_SCOPE)
async def htmx_submit_reflection_verification(
    request: Request,
    current_user: CurrentUser,
    requirement_slug: Annotated[str, Path(max_length=100)],
) -> HTMLResponse:
    """Submit a career reflection as repeated answers."""
    requirement, matches = _resolve_requirement(
        requirement_slug,
        VerificationInputShape.REFLECTION,
    )
    if requirement is None:
        return reload_page_response()
    if not matches or not isinstance(requirement, CareerReflectionRequirement):
        return _invalid_form_response(request, current_user, requirement)
    form = await _parse_verification_form(
        request,
        ReflectionVerificationForm,
        list_fields=frozenset({"answers"}),
    )
    if form is None:
        return _invalid_form_response(request, current_user, requirement)
    try:
        combined_answers = combine_reflection_answers(requirement, form.answers)
        submitted_value = submitted_value_from_raw(requirement, combined_answers)
    except ValueError as exc:
        return _invalid_form_response(request, current_user, requirement, str(exc))
    return await _submit_canonical_verification(
        request,
        current_user,
        requirement,
        submitted_value,
    )


@router.post("/github/submit", response_class=HTMLResponse)
@limiter.shared_limit("10/minute", scope=_VERIFICATION_SUBMIT_RATE_LIMIT_SCOPE)
async def htmx_submit_verification(
    request: Request,
    current_user: CurrentUser,
) -> HTMLResponse:
    """Refresh a page that still contains the retired submission form."""
    response = HTMLResponse("")
    response.headers["HX-Refresh"] = "true"
    return response


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
        return status_error_response(
            "Verification status expired. Refresh the page to check for results.",
            status_code=400,
        )

    try:
        result = await poll_verification_attempt(
            session_maker=request.app.state.session_maker,
            user_id=user_id,
            token_data=token_data,
        )
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
                "status_code": exc.status_code,
            },
        )
        return status_error_response(
            "Unable to load verification status. "
            "Refresh the page to check for results.",
            status_code=502,
        )

    if result.kind is VerificationPollKind.PROCESSING:
        requirement = get_requirement_by_slug(token_data.requirement_slug)
        if requirement is None:
            return reload_page_response()
        return render_processing(
            request,
            requirement,
            token,
            delay_seconds=_RUNNING_STATUS_DELAY_SECONDS,
        )

    if result.kind is VerificationPollKind.RELOAD:
        return reload_page_response()

    return status_error_response(
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
