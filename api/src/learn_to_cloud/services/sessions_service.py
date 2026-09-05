"""Short, committed authentication lifecycle transactions."""

import base64
import hashlib
import hmac
import logging
import secrets
from dataclasses import dataclass, field
from datetime import datetime

from fastapi import Request
from learn_to_cloud_shared.core.config import SessionConfig, get_web_settings
from learn_to_cloud_shared.repositories.auth_session_repository import (
    AuthSessionRepository,
    ResolvedSession,
)
from learn_to_cloud_shared.repositories.user_repository import UserRepository
from sqlalchemy.ext.asyncio import AsyncSession

from learn_to_cloud.core.auth import AuthenticationRequired
from learn_to_cloud.core.session_cookies import (
    AUTH_COOKIE_NAME,
    clear_cookies,
    token_digest,
)

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


def csrf_token(request: Request) -> str:
    digest = token_digest(request.cookies.get(AUTH_COOKIE_NAME))
    if digest is None:
        return ""
    return hmac.new(
        get_web_settings().session.secret_key.encode(),
        b"ltc:logout-all:v1:" + digest,
        hashlib.sha256,
    ).hexdigest()


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
            if not isinstance(resolved, ResolvedSession) or resolved.user.id != user_id:
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
