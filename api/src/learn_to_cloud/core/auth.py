"""Session identity validation, authentication dependencies, and GitHub OAuth setup."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from enum import StrEnum
from typing import Annotated

from authlib.integrations.starlette_client import OAuth
from fastapi import Depends, HTTPException, Request
from learn_to_cloud_shared.core.config import OAuthConfig, get_web_settings
from learn_to_cloud_shared.models import User
from learn_to_cloud_shared.repositories.auth_session_repository import (
    AuthSessionRepository,
    ResolvedSession,
    SessionRejection,
)

from learn_to_cloud.core.session_cookies import (
    AUTH_COOKIE_NAME,
    token_digest,
)
from learn_to_cloud.core.session_cookies import (
    SESSION_COOKIE_NAME as SESSION_COOKIE_NAME,
)

logger = logging.getLogger(__name__)

oauth = OAuth()
MAX_GITHUB_USER_ID = 2**63 - 1
MAX_USERNAME_LENGTH = 255


@dataclass(frozen=True, slots=True)
class AuthenticatedUser:
    """Authenticated identity resolved from the database."""

    user_id: int
    github_username: str


class IdentityRejectionReason(StrEnum):
    INVALID_USER_ID = "invalid_user_id"
    INVALID_GITHUB_USERNAME = "invalid_github_username"
    INVALID_RESPONSE_FORMAT = "invalid_response_format"


def validate_identity(
    user_id: object, github_username: object
) -> AuthenticatedUser | IdentityRejectionReason:
    """Return a valid user identity or the reason it was rejected."""
    if (
        not isinstance(user_id, int)
        or isinstance(user_id, bool)
        or not 0 < user_id <= MAX_GITHUB_USER_ID
    ):
        return IdentityRejectionReason.INVALID_USER_ID
    if (
        not isinstance(github_username, str)
        or not 0 < len(github_username) <= MAX_USERNAME_LENGTH
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
    """Configure the GitHub OAuth client."""
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


@dataclass(frozen=True, repr=False)
class RequestAuthentication:
    identity: AuthenticatedUser
    account: User


def get_request_user(request: Request) -> User | None:
    context = getattr(request.state, "authentication", None)
    return context.account if isinstance(context, RequestAuthentication) else None


async def get_authenticated_user_from_session(
    request: Request,
) -> AuthenticatedUser | None:
    """Resolve and touch once, releasing the transaction before route work."""
    if getattr(request.state, "auth_resolved", False):
        context = getattr(request.state, "authentication", None)
        return context.identity if isinstance(context, RequestAuthentication) else None
    request.state.authentication = None
    session = request.session
    if "user_id" in session or "github_username" in session:
        session.pop("user_id", None)
        session.pop("github_username", None)
        logger.info("auth.session.rejected", extra={"auth.session.reason": "legacy"})
    cookie = request.cookies.get(AUTH_COOKIE_NAME)
    if cookie is None:
        request.state.auth_resolved = True
        return None
    digest = token_digest(cookie)
    if digest is None:
        request.state.auth_resolved = True
        request.state.clear_auth_cookie = True
        logger.warning(
            "auth.session.rejected", extra={"auth.session.reason": "malformed"}
        )
        return None
    async with request.app.state.session_maker() as db:
        async with db.begin():
            resolved = await AuthSessionRepository(
                db, get_web_settings().session
            ).resolve_and_touch(digest)
    request.state.auth_resolved = True
    if not isinstance(resolved, ResolvedSession):
        request.state.clear_auth_cookie = True
        logger.log(
            logging.WARNING
            if resolved == SessionRejection.ACCOUNT_MISSING
            else logging.INFO,
            "auth.session.rejected",
            extra={"auth.session.reason": resolved.value},
        )
        return None
    identity = AuthenticatedUser(resolved.user.id, resolved.user.github_username)
    request.state.authentication = RequestAuthentication(identity, resolved.user)
    return identity


async def require_authenticated_user(request: Request) -> AuthenticatedUser:
    """Return the session user or raise a 401 authentication error."""
    authenticated_user = await optional_authenticated_user(request)
    if authenticated_user is None:
        raise AuthenticationRequired()
    return authenticated_user


async def optional_authenticated_user(request: Request) -> AuthenticatedUser | None:
    """Return the session user and populate request state when authenticated."""
    authenticated_user = await get_authenticated_user_from_session(request)
    if authenticated_user is not None:
        request.state.user_id = authenticated_user.user_id
        request.state.github_username = authenticated_user.github_username
    return authenticated_user


CurrentUser = Annotated[AuthenticatedUser, Depends(require_authenticated_user)]
OptionalCurrentUser = Annotated[
    AuthenticatedUser | None, Depends(optional_authenticated_user)
]
