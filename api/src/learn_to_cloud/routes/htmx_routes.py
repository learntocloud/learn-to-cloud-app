"""HTMX routes — return HTML fragments for partial page updates.

These routes handle interactive HTMX requests (step toggles, form
submissions, etc.) and return HTML partials instead of JSON.

Verification submissions persist queued attempts and return a polling card.
The worker processes attempts; authenticated polling reads their database state.
"""

import logging
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Form, Path, Query, Request
from fastapi.responses import HTMLResponse
from learn_to_cloud_shared.content_service import get_curriculum_catalog
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
from sqlalchemy.exc import SQLAlchemyError

from learn_to_cloud.core.auth import (
    AuthenticatedUser,
    CurrentAccount,
    CurrentUser,
    require_authenticated_account,
)
from learn_to_cloud.rendering.htmx_responses import (
    reload_page_response,
    render_input_error,
    render_processing,
    render_step_toggle,
    render_unavailable,
    status_error_response,
)
from learn_to_cloud.services.sessions_service import mutate_account
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
from learn_to_cloud.services.verification_attempt_service import (
    INITIAL_VERIFICATION_STATUS_DELAY_SECONDS,
    RUNNING_VERIFICATION_STATUS_DELAY_SECONDS,
    VerificationPollKind,
    poll_verification_attempt,
    submit_verification_attempt,
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

_INVALID_FORM_MESSAGE = (
    "We couldn't read this verification form. Refresh the page and try again."
)

router = APIRouter(prefix="/htmx", tags=["htmx"], include_in_schema=False)


@router.post("/steps/complete", response_class=HTMLResponse)
async def htmx_complete_step(
    db: DbSession,
    account: CurrentAccount,
    step_uuid: Annotated[UUID, Form()],
) -> HTMLResponse:
    """Complete a step and return the updated step partial."""
    try:
        topic, step, completed = await complete_step(db, account.id, step_uuid)
    except StepValidationError:
        # Step UUID doesn't exist in current content (stale cached page).
        # Force a full page reload so the user gets the current steps.
        response = HTMLResponse("")
        response.headers["HX-Refresh"] = "true"
        return response

    return render_step_toggle(account, topic, step, completed)


@router.delete("/steps/{step_uuid}", response_class=HTMLResponse)
async def htmx_uncomplete_step(
    step_uuid: UUID,
    db: DbSession,
    account: CurrentAccount,
) -> HTMLResponse:
    """Uncomplete a step and return the updated step partial."""
    try:
        topic, step, completed = await uncomplete_step(db, account.id, step_uuid)
    except StepValidationError:
        response = HTMLResponse("")
        response.headers["HX-Refresh"] = "true"
        return response

    return render_step_toggle(account, topic, step, completed)


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
    """Queue an attempt from a canonical submission value."""
    requirement_slug = requirement.slug
    try:
        attempt_id = await submit_verification_attempt(
            session_maker=request.app.state.session_maker,
            user_id=current_user.user_id,
            github_username=current_user.github_username,
            requirement_slug=requirement_slug,
            submitted_value=submitted_value,
        )
    except _USER_FACING_ERRORS as exc:
        return render_input_error(request, current_user, requirement, str(exc))
    except (SQLAlchemyError, OSError) as exc:
        logger.warning(
            "verification.submit.database_unavailable",
            extra={"error.type": type(exc).__name__},
        )
        return status_error_response(
            "Unable to submit verification. Refresh the page and try again.",
            status_code=503,
        )
    except Exception as exc:
        logger.error(
            "htmx.submit.unexpected_error",
            extra={
                "verification.requirement.slug": requirement_slug,
                "error.type": type(exc).__name__,
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

    return render_processing(
        request,
        requirement,
        attempt_id,
        delay_seconds=INITIAL_VERIFICATION_STATUS_DELAY_SECONDS,
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


@router.post(
    "/github/submit",
    response_class=HTMLResponse,
    dependencies=[Depends(require_authenticated_account)],
)
async def htmx_submit_verification() -> HTMLResponse:
    """Refresh a page that still contains the retired submission form."""
    return HTMLResponse("", headers={"HX-Refresh": "true"})


@router.get("/verification/attempts/status", response_class=HTMLResponse)
async def htmx_verification_attempt_status(
    request: Request,
    attempt_id: Annotated[UUID, Query()],
    current_user: CurrentUser,
) -> HTMLResponse:
    """Return a polling card or reload trigger for an owned persisted attempt."""
    user_id = current_user.user_id
    try:
        result = await poll_verification_attempt(
            session_maker=request.app.state.session_maker,
            user_id=user_id,
            attempt_id=attempt_id,
        )
    except (SQLAlchemyError, OSError) as exc:
        logger.warning(
            "verification.status.database_unavailable",
            extra={"error.type": type(exc).__name__},
        )
        return status_error_response(
            "Unable to load verification status. "
            "Refresh the page to check for results.",
            status_code=503,
        )

    if result is None:
        return status_error_response("Verification attempt not found.", status_code=404)

    if result.kind is VerificationPollKind.PROCESSING:
        requirement = get_curriculum_catalog().requirements_by_uuid.get(
            result.requirement_uuid
        )
        if requirement is None:
            return reload_page_response()
        return render_processing(
            request,
            requirement,
            attempt_id,
            delay_seconds=RUNNING_VERIFICATION_STATUS_DELAY_SECONDS,
        )

    if result.kind is VerificationPollKind.RELOAD:
        return reload_page_response()

    return status_error_response(
        "Verification is in an unexpected state. "
        "Refresh the page to check for results.",
        status_code=409,
    )


@router.delete("/account", response_class=HTMLResponse)
async def htmx_delete_account(
    request: Request,
    current_user: CurrentUser,
) -> HTMLResponse:
    """Delete the current user's account and redirect to home via HTMX."""
    await mutate_account(request, current_user.user_id, delete_account=True)
    response = HTMLResponse("")
    response.headers["HX-Redirect"] = "/"
    return response
