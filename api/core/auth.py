"""Session-based authentication utilities.

Provides:
- Session cookie auth via Starlette SessionMiddleware
- FastAPI dependencies for authenticated routes
- Authlib OAuth client configuration for GitHub

Session data is stored in signed cookies (via Starlette).
The session contains: user_id (GitHub numeric ID).
"""

from __future__ import annotations

from typing import Annotated

from authlib.integrations.starlette_client import OAuth
from fastapi import Depends, HTTPException, Request

from core.config import get_settings
from core.logger import get_logger
from core.wide_event import set_wide_event_fields

logger = get_logger(__name__)

# Authlib OAuth registry - configured at module level, initialized lazily
oauth = OAuth()


def init_oauth() -> None:
    """Register GitHub as an OAuth provider.

    Call once at app startup (in lifespan). Uses Authlib's built-in
    GitHub integration which knows the authorize/token/userinfo URLs.
    """
    settings = get_settings()
    if not settings.github_client_id:
        logger.warning(
            "auth.github_oauth_disabled",
            reason="GITHUB_CLIENT_ID not configured",
        )
        return

    oauth.register(
        name="github",
        client_id=settings.github_client_id,
        client_secret=settings.github_client_secret,
        access_token_url="https://github.com/login/oauth/access_token",
        authorize_url="https://github.com/login/oauth/authorize",
        api_base_url="https://api.github.com/",
        client_kwargs={"scope": "read:user user:email"},
    )
    logger.info("auth.github_oauth_configured")


def get_user_id_from_session(request: Request) -> int | None:
    """Read user_id from the session cookie.

    Returns the GitHub numeric user ID or None if not authenticated.
    """
    user_id = request.session.get("user_id")
    if user_id is not None:
        return int(user_id)
    return None


def require_auth(request: Request) -> int:
    """Dependency: raises 401 if not authenticated. Sets request.state.user_id."""
    user_id = get_user_id_from_session(request)
    if user_id is None:
        # For HTMX requests, return 401 so htmx:responseError can redirect
        # For regular requests, also 401 (page routes handle redirect themselves)
        raise HTTPException(status_code=401, detail="Unauthorized")

    request.state.user_id = user_id
    set_wide_event_fields(user_id=user_id)
    return user_id


def optional_auth(request: Request) -> int | None:
    """Dependency: returns user_id or None. Does not raise."""
    user_id = get_user_id_from_session(request)
    if user_id is not None:
        request.state.user_id = user_id
        set_wide_event_fields(user_id=user_id)
    return user_id


UserId = Annotated[int, Depends(require_auth)]
OptionalUserId = Annotated[int | None, Depends(optional_auth)]
