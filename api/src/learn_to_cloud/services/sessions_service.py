"""Session resolution dependencies and short, committed lifecycle transactions."""

import base64
import hashlib
import logging
import secrets
from dataclasses import dataclass, field
from datetime import datetime
from typing import Annotated

from fastapi import Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from learn_to_cloud.core.auth import AuthenticatedUser, AuthenticationRequired
from learn_to_cloud.core.config import SessionConfig, get_web_settings
from learn_to_cloud.core.session_cookies import (
    AUTH_COOKIE_NAME,
    clear_cookies,
    token_digest,
)
from learn_to_cloud.models import User
from learn_to_cloud.repositories.auth_session_repository import (
    AuthSessionRepository,
    SessionRejection,
)
from learn_to_cloud.repositories.user_repository import UserRepository

logger = logging.getLogger(__name__)


@dataclass(frozen=True, repr=False)
class IssuedSession:
    token: str = field(repr=False)
    expires_at: datetime
    pruned_count: int


async def issue_session(
    db: AsyncSession, config: SessionConfig, user_id: int, previous: str | None = None
) -> IssuedSession:
    """Issue inside the caller's transaction; never publish before commit."""
    raw = secrets.token_bytes(32)
    repository = AuthSessionRepository(db, config)
    record = await repository.create(user_id, hashlib.sha256(raw).digest())
    if record is None:
        raise RuntimeError("Cannot issue a session for an absent account")
    previous_digest = token_digest(previous)
    if previous_digest is not None:
        await repository.delete(previous_digest)
    count = await repository.prune_expired()
    return IssuedSession(
        base64.urlsafe_b64encode(raw).rstrip(b"=").decode(), record.expires_at, count
    )


def log_pruned(issued: IssuedSession) -> None:
    if issued.pruned_count:
        logger.info(
            "auth.session.pruned", extra={"auth.session.count": issued.pruned_count}
        )


async def revoke_current(request: Request) -> None:
    digest = token_digest(request.cookies.get(AUTH_COOKIE_NAME))
    count = 0
    if digest is not None:
        async with request.app.state.session_maker() as db:
            async with db.begin():
                count = await AuthSessionRepository(
                    db, get_web_settings().session
                ).delete(digest)
    clear_cookies(request)
    logger.info(
        "auth.session.revoked",
        extra={"auth.session.scope": "current", "auth.session.count": count},
    )


async def mutate_account(
    request: Request, user_id: int, *, delete_account: bool
) -> None:
    """Lock account before rechecking session, then revoke or delete atomically."""
    digest = token_digest(request.cookies.get(AUTH_COOKIE_NAME))
    if digest is None:
        request.state.clear_auth_cookie = True
        raise AuthenticationRequired()
    async with request.app.state.session_maker() as db:
        async with db.begin():
            repository = AuthSessionRepository(db, get_web_settings().session)
            account = await repository.lock_user(user_id)
            if account is None:
                request.state.clear_auth_cookie = True
                raise AuthenticationRequired()
            resolved = await repository.resolve_and_touch(digest)
            if not isinstance(resolved, User) or resolved.id != user_id:
                request.state.clear_auth_cookie = True
                raise AuthenticationRequired()
            if delete_account:
                await UserRepository(db).delete(user_id)
                count = 0
            else:
                count = await repository.delete_all(user_id)
    clear_cookies(request)
    if delete_account:
        logger.info("user.account_deleted")
    else:
        logger.info(
            "auth.session.revoked",
            extra={"auth.session.scope": "all", "auth.session.count": count},
        )


async def optional_authenticated_account(request: Request) -> User | None:
    """Resolve and touch once, releasing the transaction before route work."""
    if getattr(request.state, "auth_resolved", False):
        account = request.state.auth_account
        return account
    request.state.auth_account = None
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
    if not isinstance(resolved, User):
        request.state.clear_auth_cookie = True
        logger.log(
            logging.WARNING
            if resolved == SessionRejection.ACCOUNT_MISSING
            else logging.INFO,
            "auth.session.rejected",
            extra={"auth.session.reason": resolved.value},
        )
        return None
    account = resolved
    request.state.auth_account = account
    return account


OptionalCurrentAccount = Annotated[User | None, Depends(optional_authenticated_account)]


def require_authenticated_account(account: OptionalCurrentAccount) -> User:
    """Return the loaded account or raise a 401 authentication error."""
    if account is None:
        raise AuthenticationRequired()
    return account


CurrentAccount = Annotated[User, Depends(require_authenticated_account)]


def require_authenticated_user(account: CurrentAccount) -> AuthenticatedUser:
    """Return the identity of the required account."""
    return AuthenticatedUser(account.id, account.github_username)


CurrentUser = Annotated[AuthenticatedUser, Depends(require_authenticated_user)]
