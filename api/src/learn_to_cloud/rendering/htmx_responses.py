"""HTML response builders shared by HTMX route handlers."""

from __future__ import annotations

from uuid import UUID

from fastapi import Request
from fastapi.responses import HTMLResponse
from learn_to_cloud_shared.core.database import DbSession
from learn_to_cloud_shared.schemas import HandsOnRequirement, Topic

from learn_to_cloud.core.auth import AuthenticatedUser
from learn_to_cloud.core.templates import templates
from learn_to_cloud.rendering.context import (
    RequirementCardContext,
    build_checking_requirement_card_context,
    build_input_error_requirement_card_context,
    build_progress_dict,
    build_unavailable_requirement_card_context,
)
from learn_to_cloud.services.users_service import get_user_by_id


def reload_page_response() -> HTMLResponse:
    return HTMLResponse(
        "<div hx-trigger='load' "
        "hx-on::load='setTimeout(()=>location.reload(),100)'></div>"
    )


def status_error_response(
    message: str,
    *,
    status_code: int = 400,
) -> HTMLResponse:
    return HTMLResponse(
        f"<div class='text-red-600 text-sm p-2'>{message}</div>",
        status_code=status_code,
    )


def render_requirement_card(
    request: Request,
    card: RequirementCardContext,
) -> HTMLResponse:
    return templates.TemplateResponse(
        request,
        "partials/requirement_card.html",
        {"card": card},
    )


def render_input_error(
    request: Request,
    current_user: AuthenticatedUser,
    requirement: HandsOnRequirement,
    message: str,
) -> HTMLResponse:
    return render_requirement_card(
        request,
        build_input_error_requirement_card_context(
            requirement=requirement,
            github_username=current_user.github_username,
            message=message,
        ),
    )


def render_processing(
    request: Request,
    requirement: HandsOnRequirement,
    status_token: str,
    *,
    delay_seconds: int,
) -> HTMLResponse:
    return render_requirement_card(
        request,
        build_checking_requirement_card_context(
            requirement=requirement,
            verification_status_token=status_token,
            verification_status_delay_seconds=delay_seconds,
        ),
    )


def render_unavailable(
    request: Request,
    current_user: AuthenticatedUser,
    requirement: HandsOnRequirement,
    message: str,
    *,
    retryable: bool,
) -> HTMLResponse:
    return render_requirement_card(
        request,
        build_unavailable_requirement_card_context(
            requirement=requirement,
            github_username=current_user.github_username,
            message=message,
            retryable=retryable,
        ),
    )


async def render_step_toggle(
    request: Request,
    user_id: int,
    topic: Topic,
    step,
    completed_step_uuids: set[UUID],
    db: DbSession,
) -> HTMLResponse:
    user = await get_user_by_id(db, user_id)
    progress = build_progress_dict(
        len(completed_step_uuids),
        len(topic.learning_steps),
    )
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
