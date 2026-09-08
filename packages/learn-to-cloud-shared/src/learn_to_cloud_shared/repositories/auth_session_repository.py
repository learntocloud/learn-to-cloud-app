"""Digest-only session persistence; callers own transaction completion."""

from datetime import timedelta
from enum import StrEnum

from sqlalchemy import case, delete, func, or_, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from learn_to_cloud_shared.core.config import SessionConfig
from learn_to_cloud_shared.models import AuthSession, User

PRUNE_BATCH_SIZE = 100


class SessionRejection(StrEnum):
    """Bounded store rejection reasons, without credential or identity values."""

    UNKNOWN = "unknown"
    IDLE_EXPIRED = "idle_expired"
    ABSOLUTE_EXPIRED = "absolute_expired"
    ACCOUNT_MISSING = "account_missing"


class SessionDigestCollision(ValueError):
    """The generated digest already exists; retry with a fresh credential."""


def _validate_digest(token_digest: bytes) -> None:
    if not isinstance(token_digest, bytes) or len(token_digest) != 32:
        raise ValueError("Session digest must contain exactly 32 bytes.")


class AuthSessionRepository:
    """Use account-before-session locking for issuance and global mutations."""

    def __init__(self, db: AsyncSession, config: SessionConfig) -> None:
        self.db = db
        self.config = config

    async def lock_user(self, user_id: int) -> User | None:
        """Hold the account lock until caller commit, before locking sessions."""
        return await self.db.scalar(
            select(User)
            .where(User.id == user_id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )

    async def create(self, user_id: int, token_digest: bytes) -> AuthSession | None:
        """Lock the account and insert safely; None means the account is absent."""
        _validate_digest(token_digest)
        # Prevent FK diagnostics and serialize against account-wide revocation.
        if await self.lock_user(user_id) is None:
            return None
        now = func.statement_timestamp()
        result = await self.db.scalar(
            pg_insert(AuthSession)
            .values(
                token_digest=token_digest,
                user_id=user_id,
                created_at=now,
                updated_at=now,
                last_seen_at=now,
                expires_at=now
                + timedelta(seconds=self.config.absolute_timeout_seconds),
            )
            .on_conflict_do_nothing(index_elements=["token_digest"])
            .returning(AuthSession)
        )
        if result is None:
            # ON CONFLICT avoids driver DETAIL containing the credential digest.
            raise SessionDigestCollision("Generated session digest already exists.")
        return result

    async def resolve_and_touch(self, token_digest: bytes) -> User | SessionRejection:
        """Lock, then conditionally touch using a fresh database statement clock."""
        _validate_digest(token_digest)
        locked = await self.db.scalar(
            select(AuthSession.token_digest)
            .where(AuthSession.token_digest == token_digest)
            .with_for_update()
        )
        if locked is None:
            return SessionRejection.UNKNOWN
        # A separate statement samples time AFTER waiting for an existing lock.
        now = func.statement_timestamp()
        idle_cutoff = now - timedelta(seconds=self.config.idle_timeout_seconds)
        user = (
            await self.db.scalars(
                update(AuthSession)
                .where(
                    AuthSession.token_digest == token_digest,
                    AuthSession.user_id == User.id,
                    AuthSession.expires_at > now,
                    AuthSession.last_seen_at > idle_cutoff,
                )
                .values(
                    last_seen_at=func.greatest(AuthSession.last_seen_at, now),
                    updated_at=func.greatest(AuthSession.updated_at, now),
                )
                .returning(User)
                .execution_options(synchronize_session=False, populate_existing=True)
            )
        ).one_or_none()
        if user is not None:
            return user
        reason = await self.db.scalar(
            select(
                case(
                    (User.id.is_(None), SessionRejection.ACCOUNT_MISSING.value),
                    (
                        AuthSession.expires_at <= now,
                        SessionRejection.ABSOLUTE_EXPIRED.value,
                    ),
                    else_=SessionRejection.IDLE_EXPIRED.value,
                )
            )
            .select_from(AuthSession)
            .outerjoin(User, User.id == AuthSession.user_id)
            .where(AuthSession.token_digest == token_digest)
        )
        return SessionRejection(reason) if reason else SessionRejection.UNKNOWN

    async def delete(self, token_digest: bytes) -> int:
        """Delete one credential, including an expired credential."""
        _validate_digest(token_digest)
        result = await self.db.execute(
            delete(AuthSession)
            .where(AuthSession.token_digest == token_digest)
            .returning(AuthSession.token_digest)
        )
        return len(result.all())

    async def delete_all(self, user_id: int) -> int:
        """Lock the account, then revoke all its sessions in this transaction."""
        if await self.lock_user(user_id) is None:
            return 0
        result = await self.db.execute(
            delete(AuthSession)
            .where(AuthSession.user_id == user_id)
            .returning(AuthSession.token_digest)
        )
        return len(result.all())

    async def prune_expired(self) -> int:
        """Delete at most 100 expired rows, skipping concurrent session work."""
        now = func.statement_timestamp()
        expired = select(AuthSession.token_digest).where(
            or_(
                AuthSession.expires_at <= now,
                AuthSession.last_seen_at
                <= now - timedelta(seconds=self.config.idle_timeout_seconds),
            )
        )
        candidates = expired.limit(PRUNE_BATCH_SIZE).with_for_update(skip_locked=True)
        result = await self.db.execute(
            delete(AuthSession)
            .where(AuthSession.token_digest.in_(candidates))
            .returning(AuthSession.token_digest)
            .execution_options(synchronize_session=False)
        )
        return len(result.all())
