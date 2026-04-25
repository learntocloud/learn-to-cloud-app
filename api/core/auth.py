"""Session-based authentication utilities.

Provides:
- Session cookie auth via Starlette SessionMiddleware
- FastAPI dependencies for authenticated routes
- Authlib OAuth client configuration for GitHub

Session data is stored in signed cookies (via Starlette).
The session contains: user_id (GitHub numeric ID).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Annotated

from authlib.integrations.starlette_client import OAuth
from fastapi import Depends, HTTPException, Request

from core.config import get_settings

logger = logging.getLogger(__name__)

oauth = OAuth()


@dataclass(frozen=True, slots=True)
class AuthenticatedUser:
    """Authenticated identity stored in the session cookie."""

    user_id: int
    github_username: str | None


def init_oauth() -> None:
    """Register GitHub as an OAuth provider.

    Call once at app startup (in lifespan). Uses Authlib's built-in
    GitHub integration which knows the authorize/token/userinfo URLs.
    """
    settings = get_settings()
    if not settings.github_client_id:
        logger.warning(
            "auth.github_oauth_disabled",
            extra={"reason": "github_client_id_not_configured"},
        )
        return

    oauth.register(
        name="github",
        client_id=settings.github_client_id,
        client_secret=settings.github_client_secret,
        access_token_url="https://github.com/login/oauth/access_token",
        authorize_url="https://github.com/login/oauth/authorize",
        api_base_url="https://api.github.com/",
        client_kwargs={"scope": "read:user"},
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


def get_github_username_from_session(request: Request) -> str | None:
    """Read github_username from the session cookie."""
    github_username = request.session.get("github_username")
    if isinstance(github_username, str) and github_username:
        return github_username
    return None


def get_authenticated_user_from_session(request: Request) -> AuthenticatedUser | None:
    """Read authenticated identity from the session cookie."""
    user_id = get_user_id_from_session(request)
    if user_id is None:
        return None
    return AuthenticatedUser(
        user_id=user_id,
        github_username=get_github_username_from_session(request),
    )


def _unauthenticated_exception(request: Request) -> HTTPException:
    is_htmx = request.headers.get("hx-request") == "true"
    if is_htmx:
        return HTTPException(status_code=401, detail="Unauthorized")
    return HTTPException(
        status_code=307,
        headers={"Location": "/auth/login"},
    )


def require_auth(request: Request) -> int:
    """Dependency: raises 401 if not authenticated. Sets request.state.user_id.

    For HTMX requests, returns 401 so the htmx:responseError handler
    can redirect client-side. For regular browser page requests,
    redirects to /auth/login directly.
    """
    return require_authenticated_user(request).user_id


def optional_auth(request: Request) -> int | None:
    """Dependency: returns user_id or None. Does not raise."""
    authenticated_user = optional_authenticated_user(request)
    if authenticated_user is None:
        return None
    return authenticated_user.user_id


def require_authenticated_user(request: Request) -> AuthenticatedUser:
    """Dependency: returns session identity or raises if not authenticated."""
    authenticated_user = optional_authenticated_user(request)
    if authenticated_user is None:
        raise _unauthenticated_exception(request)
    return authenticated_user


def optional_authenticated_user(request: Request) -> AuthenticatedUser | None:
    """Dependency: returns session identity or None. Does not raise."""
    authenticated_user = get_authenticated_user_from_session(request)
    if authenticated_user is not None:
        request.state.user_id = authenticated_user.user_id
        request.state.github_username = authenticated_user.github_username
    return authenticated_user


UserId = Annotated[int, Depends(require_auth)]
OptionalUserId = Annotated[int | None, Depends(optional_auth)]
CurrentUser = Annotated[AuthenticatedUser, Depends(require_authenticated_user)]
OptionalCurrentUser = Annotated[
    AuthenticatedUser | None, Depends(optional_authenticated_user)
]
