"""Session-based authentication utilities.

Provides:
- Session cookie auth via Starlette SessionMiddleware
- FastAPI dependencies for authenticated routes
- Authlib OAuth client configuration for GitHub

Session data is stored in signed cookies (via Starlette).
The session contains user_id (GitHub numeric ID) and github_username.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from enum import StrEnum
from typing import Annotated

from authlib.integrations.starlette_client import OAuth
from fastapi import Depends, HTTPException, Request
from learn_to_cloud_shared.core.config import OAuthConfig

logger = logging.getLogger(__name__)

oauth = OAuth()
SESSION_COOKIE_NAME = "session"


@dataclass(frozen=True, slots=True)
class AuthenticatedUser:
    """Authenticated identity stored in the session cookie."""

    user_id: int
    github_username: str


class IdentityRejectionReason(StrEnum):
    INCOMPLETE_IDENTITY = "incomplete_identity"
    INVALID_USER_ID = "invalid_user_id"
    INVALID_GITHUB_USERNAME = "invalid_github_username"
    INVALID_PROFILE = "invalid_profile"


def validate_identity(
    user_id: object, github_username: object
) -> AuthenticatedUser | IdentityRejectionReason:
    """Validate identity data without coercion or GitHub naming rules."""
    if (
        not isinstance(user_id, int)
        or isinstance(user_id, bool)
        or not 0 < user_id < 2**63
    ):
        return IdentityRejectionReason.INVALID_USER_ID
    if (
        not isinstance(github_username, str)
        or not 0 < len(github_username) <= 255
        or not github_username.strip()
        or "\x00" in github_username
    ):
        return IdentityRejectionReason.INVALID_GITHUB_USERNAME
    try:
        github_username.encode("utf-8")
    except UnicodeEncodeError:
        return IdentityRejectionReason.INVALID_GITHUB_USERNAME
    return AuthenticatedUser(user_id=user_id, github_username=github_username)


class AuthenticationRequired(HTTPException):
    """The request has no authenticated session identity."""

    def __init__(self) -> None:
        super().__init__(status_code=401, detail="Unauthorized")


def init_oauth(settings: OAuthConfig) -> None:
    """Register GitHub as an OAuth provider.

    Call once at app startup (in lifespan). Uses Authlib's built-in
    GitHub integration which knows the authorize/token/userinfo URLs.
    """
    if not settings.client_id:
        logger.warning(
            "auth.github_oauth_disabled",
            extra={"auth.configuration.reason": "github_client_id_not_configured"},
        )
        return

    oauth.register(
        name="github",
        client_id=settings.client_id,
        client_secret=settings.client_secret,
        access_token_url="https://github.com/login/oauth/access_token",
        authorize_url="https://github.com/login/oauth/authorize",
        api_base_url="https://api.github.com/",
        client_kwargs={"scope": "read:user"},
    )


def get_authenticated_user_from_session(request: Request) -> AuthenticatedUser | None:
    """Read valid identity, removing malformed identity but preserving OAuth state."""
    session = request.session
    if "user_id" not in session and "github_username" not in session:
        return None
    identity = (
        IdentityRejectionReason.INCOMPLETE_IDENTITY
        if "user_id" not in session or "github_username" not in session
        else validate_identity(session["user_id"], session["github_username"])
    )
    if isinstance(identity, AuthenticatedUser):
        return identity
    session.pop("user_id", None)
    session.pop("github_username", None)
    logger.warning(
        "auth.session.identity_rejected",
        extra={"auth.identity.reason": identity.value},
    )
    return None


def require_authenticated_user(request: Request) -> AuthenticatedUser:
    """Require a session identity, returning 401 when unauthenticated."""
    authenticated_user = optional_authenticated_user(request)
    if authenticated_user is None:
        raise AuthenticationRequired()
    return authenticated_user


def optional_authenticated_user(request: Request) -> AuthenticatedUser | None:
    """Dependency: returns session identity or None. Does not raise."""
    authenticated_user = get_authenticated_user_from_session(request)
    if authenticated_user is not None:
        request.state.user_id = authenticated_user.user_id
        request.state.github_username = authenticated_user.github_username
    return authenticated_user


CurrentUser = Annotated[AuthenticatedUser, Depends(require_authenticated_user)]
OptionalCurrentUser = Annotated[
    AuthenticatedUser | None, Depends(optional_authenticated_user)
]
