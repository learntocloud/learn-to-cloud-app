"""GitHub OAuth login, callback, and logout routes."""

import hmac
import logging
from json import JSONDecodeError
from time import time

import httpx2
from authlib.integrations.starlette_client import OAuthError
from fastapi import APIRouter, Form, HTTPException, Request
from fastapi.responses import RedirectResponse
from learn_to_cloud_shared.core.config import get_web_settings
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from learn_to_cloud.core.auth import (
    AuthenticatedUser,
    CurrentUser,
    IdentityRejectionReason,
    oauth,
    validate_identity,
)
from learn_to_cloud.core.session_cookies import AUTH_COOKIE_NAME, issue_cookie
from learn_to_cloud.services.sessions_service import (
    csrf_token,
    issue_session,
    log_pruned,
    mutate_account,
    revoke_current,
)
from learn_to_cloud.services.users_service import (
    get_or_create_user_from_github,
    normalize_github_username,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/auth", tags=["auth"])


def _prepare_oauth_state(request: Request) -> dict:
    """Discard obsolete identities and expired handshakes, retaining live tabs."""
    request.session.pop("user_id", None)
    request.session.pop("github_username", None)
    now = time()
    for key, value in list(request.session.items()):
        if key.startswith("_state_github_") and (
            not isinstance(value, dict)
            or not isinstance(value.get("exp"), (int, float))
            or value["exp"] <= now
        ):
            request.session.pop(key)
    return dict(request.session)


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

    previous_states = _prepare_oauth_state(request)
    github.framework.expires_in = get_web_settings().session.oauth_state_max_age_seconds
    redirect_uri = str(request.url_for("auth_callback"))
    # Azure Container Apps terminates TLS at the load balancer; ensure
    # the redirect URI uses https so it matches the GitHub OAuth config.
    if get_web_settings().web_security.require_https and redirect_uri.startswith(
        "http://"
    ):
        redirect_uri = redirect_uri.replace("http://", "https://", 1)
    response = await github.authorize_redirect(request, redirect_uri)
    for key, value in previous_states.items():
        request.session.setdefault(key, value)
    return response


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

    _prepare_oauth_state(request)
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
        issued = await issue_session(
            db,
            get_web_settings().session,
            user.id,
            request.cookies.get(AUTH_COOKIE_NAME),
        )
        await db.commit()

    request.session.pop("user_id", None)
    request.session.pop("github_username", None)
    response = RedirectResponse(url="/dashboard", status_code=302)
    issue_cookie(request, response, issued.token, issued.expires_at)
    logger.info("auth.login.success")
    log_pruned(issued)

    return response


@router.post(
    "/logout",
    summary="Log out and clear session",
    include_in_schema=False,
)
async def logout(request: Request) -> RedirectResponse:
    """Revoke this browser's credential before clearing its cookies."""
    await revoke_current(request)
    return RedirectResponse(url="/", status_code=303)


@router.post("/logout-all", include_in_schema=False)
async def logout_all(
    request: Request, current_user: CurrentUser, csrf: str = Form("")
) -> RedirectResponse:
    """Revoke every current session, including this browser."""
    expected = csrf_token(request)
    if not expected or not hmac.compare_digest(expected.encode(), csrf.encode()):
        raise HTTPException(status_code=403, detail="Invalid confirmation token")
    await mutate_account(request, current_user.user_id, delete_account=False)
    return RedirectResponse(url="/", status_code=303)
