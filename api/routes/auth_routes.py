"""GitHub OAuth authentication routes.

Handles:
- GET /auth/login — redirect to GitHub OAuth authorize
- GET /auth/callback — exchange code for token, create session
- POST /auth/logout — clear session, redirect to home
"""

import logging

from authlib.integrations.starlette_client import OAuthError
from fastapi import APIRouter, Request
from fastapi.responses import RedirectResponse

from core.auth import oauth
from core.config import get_settings
from core.database import DbSession
from core.ratelimit import limiter
from services.users_service import get_or_create_user_from_github, parse_display_name

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/auth", tags=["auth"])


@router.get(
    "/login",
    summary="Redirect to GitHub OAuth login",
    include_in_schema=False,
)
async def login(request: Request) -> RedirectResponse:
    """Initiate GitHub OAuth flow.

    Redirects the user to GitHub's authorization page.
    After granting access, GitHub redirects back to /auth/callback.
    """
    github = oauth.create_client("github")
    if github is None:
        logger.error("auth.login.github_not_configured")
        return RedirectResponse(url="/", status_code=302)

    redirect_uri = str(request.url_for("auth_callback"))
    # Azure Container Apps terminates TLS at the load balancer; ensure
    # the redirect URI uses https so it matches the GitHub OAuth config.
    if get_settings().require_https and redirect_uri.startswith("http://"):
        redirect_uri = redirect_uri.replace("http://", "https://", 1)
    # Show the account picker so users can switch accounts (see issue #94).
    # prompt=select_account shows the picker without forcing re-authorization.
    return await github.authorize_redirect(
        request, redirect_uri, prompt="select_account"
    )


@router.get(
    "/callback",
    name="auth_callback",
    summary="GitHub OAuth callback",
    include_in_schema=False,
)
async def callback(request: Request, db: DbSession) -> RedirectResponse:
    """Handle GitHub OAuth callback.

    Exchanges the authorization code for an access token, fetches the
    user's GitHub profile, creates or updates the user in the database,
    and sets the session cookie.
    """
    github = oauth.create_client("github")
    if github is None:
        logger.error("auth.callback.github_not_configured")
        return RedirectResponse(url="/", status_code=302)

    try:
        token = await github.authorize_access_token(request)
    except OAuthError:
        logger.exception("auth.callback.token_exchange_failed")
        return RedirectResponse(url="/", status_code=302)

    resp = await github.get("user", token=token)
    github_user = resp.json()

    github_id = github_user.get("id")
    if github_id is None:
        logger.error(
            "auth.callback.missing_github_id",
            extra={"status_code": getattr(resp, "status_code", None)},
        )
        return RedirectResponse(url="/", status_code=302)

    github_username = github_user.get("login", "")
    avatar_url = github_user.get("avatar_url")
    first_name, last_name = parse_display_name(github_user.get("name", ""))

    user = await get_or_create_user_from_github(
        db=db,
        github_id=github_id,
        first_name=first_name,
        last_name=last_name,
        avatar_url=avatar_url,
        github_username=github_username.lower(),
    )

    request.session["user_id"] = user.id
    request.session["github_username"] = user.github_username or ""

    logger.info(
        "auth.login.success",
        extra={"user_id": user.id, "github_username": github_username},
    )

    return RedirectResponse(url="/dashboard", status_code=302)


@router.post(
    "/logout",
    summary="Log out and clear session",
    include_in_schema=False,
)
@limiter.limit("10/minute")
async def logout(request: Request) -> RedirectResponse:
    """Clear the session cookie and redirect to home."""
    user_id = request.session.get("user_id")
    request.session.clear()

    if user_id:
        logger.info("auth.logout", extra={"user_id": user_id})

    return RedirectResponse(url="/", status_code=302)
