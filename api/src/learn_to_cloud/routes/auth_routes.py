"""GitHub OAuth authentication routes.

Handles:
- GET /auth/login — redirect to GitHub OAuth authorize
- GET /auth/callback — exchange code for token, create session
- POST /auth/logout — clear session, redirect to home
"""

import logging
import time

import httpx
from authlib.integrations.starlette_client import OAuthError
from fastapi import APIRouter, Request
from fastapi.responses import RedirectResponse
from learn_to_cloud_shared.core.config import get_settings
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from learn_to_cloud.core.auth import UserId, oauth
from learn_to_cloud.core.ratelimit import limiter
from learn_to_cloud.services.users_service import (
    get_or_create_user_from_github,
    parse_display_name,
)

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
    return await github.authorize_redirect(request, redirect_uri)


@router.get(
    "/callback",
    name="auth_callback",
    summary="GitHub OAuth callback",
    include_in_schema=False,
)
async def callback(request: Request) -> RedirectResponse:
    """Handle GitHub OAuth callback.

    Exchanges the authorization code for an access token, fetches the
    user's GitHub profile, creates or updates the user in the database,
    and sets the session cookie.

    DB session is acquired only after GitHub API calls complete to avoid
    holding a connection idle during external HTTP round-trips.
    """
    github = oauth.create_client("github")
    if github is None:
        logger.error("auth.callback.github_not_configured")
        return RedirectResponse(url="/", status_code=302)

    try:
        t0 = time.perf_counter()
        token = await github.authorize_access_token(request)
    except (OAuthError, httpx.HTTPStatusError, httpx.ReadTimeout) as exc:
        logger.error(
            "auth.callback.token_exchange_failed",
            extra={
                "exc_type": type(exc).__name__,
                "exc_message": str(exc),
            },
        )
        return RedirectResponse(url="/", status_code=302)

    t1 = time.perf_counter()
    resp = await github.get("user", token=token)
    t2 = time.perf_counter()
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

    # Acquire DB session only now — GitHub API calls are done.
    sm: async_sessionmaker[AsyncSession] = request.app.state.session_maker
    async with sm() as db:
        user = await get_or_create_user_from_github(
            db=db,
            github_id=github_id,
            first_name=first_name,
            last_name=last_name,
            avatar_url=avatar_url,
            github_username=github_username.lower(),
        )
        await db.commit()
    t3 = time.perf_counter()

    request.session["user_id"] = user.id
    request.session["github_username"] = user.github_username or ""

    logger.info(
        "auth.login.success",
        extra={
            "user_id": user.id,
            "github_username": github_username,
            "token_exchange_ms": round((t1 - t0) * 1000, 1),
            "github_user_fetch_ms": round((t2 - t1) * 1000, 1),
            "db_upsert_ms": round((t3 - t2) * 1000, 1),
            "total_ms": round((t3 - t0) * 1000, 1),
        },
    )

    return RedirectResponse(url="/dashboard", status_code=302)


@router.post(
    "/logout",
    summary="Log out and clear session",
    include_in_schema=False,
)
@limiter.limit("10/minute")
async def logout(request: Request, user_id: UserId) -> RedirectResponse:
    """Clear the session cookie and redirect to home."""
    request.session.clear()

    if user_id:
        logger.info("auth.logout", extra={"user_id": user_id})

    return RedirectResponse(url="/", status_code=302)
