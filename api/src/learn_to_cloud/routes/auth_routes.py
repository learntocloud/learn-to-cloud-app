"""GitHub OAuth login, callback, and logout routes."""

import logging
from json import JSONDecodeError

import httpx2
from authlib.integrations.starlette_client import OAuthError
from fastapi import APIRouter, Request
from fastapi.responses import RedirectResponse
from learn_to_cloud_shared.core.config import get_web_settings
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from learn_to_cloud.core.auth import (
    SESSION_COOKIE_NAME,
    AuthenticatedUser,
    IdentityRejectionReason,
    oauth,
    validate_identity,
)
from learn_to_cloud.services.users_service import (
    get_or_create_user_from_github,
    normalize_github_username,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/auth", tags=["auth"])


def _reject_identity(reason: IdentityRejectionReason) -> RedirectResponse:
    logger.warning(
        "auth.callback.identity_rejected",
        extra={"auth.identity.reason": reason.value},
    )
    return RedirectResponse(url="/", status_code=302)


@router.get(
    "/login",
    summary="Redirect to GitHub OAuth login",
    include_in_schema=False,
)
async def login(request: Request) -> RedirectResponse:
    """Redirect to GitHub to start OAuth login."""
    github = oauth.create_client("github")
    if github is None:
        logger.error("auth.login.github_not_configured")
        return RedirectResponse(url="/", status_code=302)

    redirect_uri = str(request.url_for("auth_callback"))
    # Azure Container Apps terminates TLS at the load balancer; ensure
    # the redirect URI uses https so it matches the GitHub OAuth config.
    if get_web_settings().web_security.require_https and redirect_uri.startswith(
        "http://"
    ):
        redirect_uri = redirect_uri.replace("http://", "https://", 1)
    return await github.authorize_redirect(request, redirect_uri)


@router.get(
    "/callback",
    name="auth_callback",
    summary="GitHub OAuth callback",
    include_in_schema=False,
)
async def callback(request: Request) -> RedirectResponse:
    """Validate the user ID and username, save the user, and create a session."""
    github = oauth.create_client("github")
    if github is None:
        logger.error("auth.callback.github_not_configured")
        return RedirectResponse(url="/", status_code=302)

    try:
        token = await github.authorize_access_token(request)
    except (OAuthError, httpx2.HTTPError) as exc:
        logger.warning(
            "auth.callback.token_exchange_failed",
            extra={"error.type": type(exc).__name__},
        )
        return RedirectResponse(url="/", status_code=302)

    try:
        resp = await github.get("user", token=token)
        resp.raise_for_status()
    except httpx2.HTTPError as exc:
        logger.warning(
            "auth.callback.profile_fetch_failed",
            extra={"error.type": type(exc).__name__},
        )
        return RedirectResponse(url="/", status_code=302)

    try:
        github_user = resp.json()
    except (JSONDecodeError, UnicodeDecodeError):
        return _reject_identity(IdentityRejectionReason.INVALID_RESPONSE_FORMAT)
    if not isinstance(github_user, dict):
        return _reject_identity(IdentityRejectionReason.INVALID_RESPONSE_FORMAT)

    identity = validate_identity(github_user.get("id"), github_user.get("login"))
    if not isinstance(identity, AuthenticatedUser):
        return _reject_identity(identity)
    normalized_identity = validate_identity(
        identity.user_id, normalize_github_username(identity.github_username)
    )
    if not isinstance(normalized_identity, AuthenticatedUser):
        return _reject_identity(normalized_identity)

    avatar_url = github_user.get("avatar_url")

    sm: async_sessionmaker[AsyncSession] = request.app.state.session_maker
    async with sm() as db:
        user = await get_or_create_user_from_github(
            db=db,
            github_id=normalized_identity.user_id,
            display_name=github_user.get("name"),
            avatar_url=avatar_url,
            github_username=normalized_identity.github_username,
        )
        persisted_identity = validate_identity(user.id, user.github_username)
        if (
            not isinstance(persisted_identity, AuthenticatedUser)
            or persisted_identity != normalized_identity
        ):
            raise RuntimeError(
                "Persisted OAuth identity does not match validated identity"
            )
        await db.commit()

    request.session["user_id"] = persisted_identity.user_id
    request.session["github_username"] = persisted_identity.github_username
    logger.info("auth.login.success")

    return RedirectResponse(url="/dashboard", status_code=302)


@router.post(
    "/logout",
    summary="Log out and clear session",
    include_in_schema=False,
)
async def logout(request: Request) -> RedirectResponse:
    """Clear the session cookie and redirect to home."""
    request.session.clear()
    response = RedirectResponse(url="/", status_code=303)
    # Rejected cookies look like empty sessions to SessionMiddleware.
    response.delete_cookie(
        SESSION_COOKIE_NAME,
        path="/",
        secure=get_web_settings().web_security.require_https,
        httponly=True,
        samesite="lax",
    )
    return response
