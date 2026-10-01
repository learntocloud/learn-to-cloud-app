"""Session identity validation, authentication errors, and GitHub OAuth setup."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from enum import StrEnum

import httpx2
from authlib.integrations.starlette_client import OAuth
from fastapi import HTTPException

from learn_to_cloud.core.config import OAuthConfig
from learn_to_cloud.core.outbound import Dependency, send_measured

logger = logging.getLogger(__name__)


class _MeasuredOAuthTransport(httpx2.AsyncBaseTransport):
    """Shared, measured httpx2 transport for authlib's per-call OAuth clients."""

    def __init__(self) -> None:
        self._inner = httpx2.AsyncHTTPTransport()

    async def handle_async_request(self, request: httpx2.Request) -> httpx2.Response:
        return await send_measured(self._inner, Dependency.GITHUB_OAUTH, request)

    async def aclose(self) -> None:
        """Keep the pool open; authlib closes its client after every call."""

    async def close_pool(self) -> None:
        await self._inner.aclose()


oauth = OAuth()
oauth_transport = _MeasuredOAuthTransport()
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
        client_kwargs={"scope": "read:user", "transport": oauth_transport},
    )
