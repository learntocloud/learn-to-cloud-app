"""Session issuance transaction ownership, rollback, and credential privacy."""

import hashlib
from base64 import urlsafe_b64decode
from unittest.mock import patch

import pytest
from learn_to_cloud_shared.models import AuthSession, User
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import async_sessionmaker

from learn_to_cloud.core.session_cookies import token_digest
from learn_to_cloud.services.sessions_service import issue_session

pytestmark = pytest.mark.integration


@pytest.fixture
async def maker(test_engine):
    maker = async_sessionmaker(test_engine, expire_on_commit=False)
    async with maker() as db, db.begin():
        db.add(User(id=42, github_username="testuser"))
    return maker


async def test_random_opaque_digest_only_and_no_implicit_commit(maker, test_settings):
    async with maker() as db:
        issued = await issue_session(db, test_settings.session, 42)
        assert issued.token not in repr(issued)
        raw = urlsafe_b64decode(issued.token + "=")
        assert len(raw) == 32
        digest = hashlib.sha256(raw).digest()
        assert digest == token_digest(issued.token)
        row = await db.get(AuthSession, digest)
        assert row.user_id == 42
        assert (
            row.expires_at - row.created_at
        ).total_seconds() == test_settings.session.absolute_timeout_seconds
        async with maker() as other:
            assert await other.get(AuthSession, digest) is None
        await db.commit()
    async with maker() as other:
        assert await other.get(AuthSession, digest) is not None


async def test_failed_issuance_rolls_back_rotation_and_pruning(maker, test_settings):
    async with maker() as db, db.begin():
        old = await issue_session(db, test_settings.session, 42)
    with patch(
        "learn_to_cloud.services.sessions_service.AuthSessionRepository.prune_expired",
        side_effect=RuntimeError("pruning failed"),
    ):
        with pytest.raises(RuntimeError, match="pruning failed"):
            async with maker() as db, db.begin():
                await issue_session(db, test_settings.session, 42, old.token)
    async with maker() as db:
        assert await db.get(AuthSession, token_digest(old.token)) is not None
        assert await db.scalar(select(func.count()).select_from(AuthSession)) == 1


async def test_absent_user_does_not_issue(maker, test_settings):
    with pytest.raises(RuntimeError, match="absent account"):
        async with maker() as db, db.begin():
            await issue_session(db, test_settings.session, 999)
    async with maker() as db:
        assert await db.scalar(select(func.count()).select_from(AuthSession)) == 0


async def test_later_successful_login_prunes_expired_rows(maker, test_settings):
    async with maker() as db, db.begin():
        expired = await issue_session(db, test_settings.session, 42)
        await db.execute(
            update(AuthSession).values(expires_at=func.statement_timestamp())
        )
    async with maker() as db, db.begin():
        active = await issue_session(db, test_settings.session, 42)
        assert active.pruned_count == 1
    async with maker() as db:
        assert await db.get(AuthSession, token_digest(expired.token)) is None
        assert await db.get(AuthSession, token_digest(active.token)) is not None
