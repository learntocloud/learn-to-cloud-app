"""Real PostgreSQL lifetime, transaction, and concurrent revocation coverage."""

import asyncio
import traceback
from datetime import timedelta
from types import SimpleNamespace

import pytest
from sqlalchemy import delete, func, literal, select, text, update
from sqlalchemy.ext.asyncio import async_sessionmaker

from learn_to_cloud_shared.core.config import SessionConfig
from learn_to_cloud_shared.models import AuthSession, User
from learn_to_cloud_shared.repositories import auth_session_repository as module
from learn_to_cloud_shared.repositories.auth_session_repository import (
    AuthSessionRepository,
    ResolvedSession,
    SessionDigestCollision,
    SessionRejection,
)

pytestmark = pytest.mark.integration
CONFIG = SessionConfig()
DIGEST = bytes(range(32))


async def seed(db, count=1):
    db.add(User(id=1, github_username="learner"))
    await db.flush()
    repo = AuthSessionRepository(db, CONFIG)
    sessions = [
        await repo.create(1, i.to_bytes(32, "big")) for i in range(1, count + 1)
    ]
    return repo, sessions


async def test_create_clock_collision_missing_account_and_rollback(db_session):
    repo, sessions = await seed(db_session)
    session = sessions[0]
    assert session is not None
    assert session.created_at == session.updated_at == session.last_seen_at
    assert session.expires_at - session.created_at == timedelta(days=30)
    assert session.created_at <= await db_session.scalar(select(func.clock_timestamp()))
    with pytest.raises(SessionDigestCollision) as caught:
        await repo.create(1, session.token_digest)
    formatted = "".join(traceback.format_exception(caught.value))
    assert session.token_digest.hex() not in formatted
    assert caught.value.__cause__ is None
    assert await repo.create(9999, DIGEST) is None
    assert await db_session.scalar(select(func.count()).select_from(AuthSession)) == 1


@pytest.mark.parametrize("digest", [b"", b"short", b"x" * 33, "not-bytes"])
async def test_invalid_digest_rejected_before_sql(db_session, digest):
    repo = AuthSessionRepository(db_session, CONFIG)
    for operation in (repo.resolve_and_touch, repo.delete):
        with pytest.raises(ValueError, match="exactly 32 bytes"):
            await operation(digest)
    with pytest.raises(ValueError, match="exactly 32 bytes"):
        await repo.create(1, digest)


@pytest.mark.parametrize("kind", ["idle", "absolute"])
@pytest.mark.parametrize("offset", [-1, 0, 1])
async def test_exact_database_expiry_boundaries(db_session, monkeypatch, kind, offset):
    repo, sessions = await seed(db_session)
    session = sessions[0]
    now = await db_session.scalar(select(func.statement_timestamp()))
    # Freeze only this repository's SQL clock at a database-produced timestamp.
    monkeypatch.setattr(
        module,
        "func",
        SimpleNamespace(
            statement_timestamp=lambda: literal(now), greatest=func.greatest
        ),
    )
    values = (
        {"last_seen_at": now - timedelta(days=7) + timedelta(microseconds=offset)}
        if kind == "idle"
        else {"expires_at": now + timedelta(microseconds=offset)}
    )
    await db_session.execute(
        update(AuthSession)
        .values(**values)
        .execution_options(synchronize_session=False)
    )
    result = await repo.resolve_and_touch(session.token_digest)
    if offset > 0:
        assert isinstance(result, ResolvedSession)
    else:
        assert result == (
            SessionRejection.IDLE_EXPIRED
            if kind == "idle"
            else SessionRejection.ABSOLUTE_EXPIRED
        )
        stored = (await db_session.execute(select(AuthSession.__table__))).one()
        for key, value in values.items():
            assert stored._mapping[key] == value


async def test_touch_current_user_monotonic_and_absolute_unchanged(db_session):
    repo, sessions = await seed(db_session)
    session = sessions[0]
    created, expires = session.created_at, session.expires_at
    future = created + timedelta(hours=1)
    await db_session.execute(
        update(AuthSession).values(last_seen_at=future, updated_at=future)
    )
    stale_user = await db_session.get(User, 1)
    await db_session.execute(
        update(User)
        .values(github_username="renamed")
        .execution_options(synchronize_session=False)
    )
    assert stale_user.github_username == "learner"
    result = await repo.resolve_and_touch(session.token_digest)
    assert isinstance(result, ResolvedSession)
    assert result.user.github_username == "renamed"
    assert result.session.last_seen_at == result.session.updated_at == future
    assert (result.session.created_at, result.session.expires_at) == (created, expires)
    assert "renamed" not in repr(result)
    assert session.token_digest.hex() not in repr(result)


async def test_transaction_clock_does_not_freeze_session_activity(db_session):
    repo, sessions = await seed(db_session)
    before = sessions[0].last_seen_at
    await db_session.execute(text("SELECT pg_sleep(0.02)"))
    result = await repo.resolve_and_touch(sessions[0].token_digest)
    assert isinstance(result, ResolvedSession)
    assert result.session.last_seen_at > before


async def test_delete_independent_session_and_account_cascade_recreation(db_session):
    repo, sessions = await seed(db_session, 2)
    first, second = [s.token_digest for s in sessions]
    assert await repo.delete(first) == 1
    assert await repo.delete(first) == 0
    assert await repo.resolve_and_touch(first) == SessionRejection.UNKNOWN
    assert isinstance(await repo.resolve_and_touch(second), ResolvedSession)
    await db_session.execute(delete(User).where(User.id == 1))
    db_session.expunge_all()
    db_session.add(User(id=1, github_username="recreated"))
    await db_session.flush()
    assert await repo.resolve_and_touch(second) == SessionRejection.UNKNOWN
    assert await repo.create(1, DIGEST) is not None
    assert await repo.delete_all(1) == 1
    assert await repo.delete_all(9999) == 0


async def test_prune_bounded_both_expiries_and_rollback(db_session):
    repo, sessions = await seed(db_session, 205)
    now = func.statement_timestamp()
    await db_session.execute(
        update(AuthSession)
        .where(AuthSession.token_digest.in_([s.token_digest for s in sessions[:100]]))
        .values(expires_at=now)
    )
    await db_session.execute(
        update(AuthSession)
        .where(
            AuthSession.token_digest.in_([s.token_digest for s in sessions[100:203]])
        )
        .values(last_seen_at=now - timedelta(days=7))
    )
    async with db_session.begin_nested() as savepoint:
        assert await repo.prune_expired() == 100
        await savepoint.rollback()
    assert await db_session.scalar(select(func.count()).select_from(AuthSession)) == 205
    assert [await repo.prune_expired() for _ in range(4)] == [100, 100, 3, 0]
    for session in sessions[203:]:
        assert isinstance(
            await repo.resolve_and_touch(session.token_digest), ResolvedSession
        )


async def committed_seed(test_engine, count=1):
    maker = async_sessionmaker(test_engine, expire_on_commit=False)
    async with maker.begin() as db:
        _, sessions = await seed(db, count)
        digests = [s.token_digest for s in sessions]
    return maker, digests


async def assert_waiting(task):
    with pytest.raises(TimeoutError):
        await asyncio.wait_for(asyncio.shield(task), timeout=0.1)


@pytest.mark.parametrize("delete_first", [False, True])
async def test_concurrent_touch_and_logout_cannot_revive(test_engine, delete_first):
    maker, (digest,) = await committed_seed(test_engine)
    async with maker() as first:
        repo = AuthSessionRepository(first, CONFIG)
        if delete_first:
            assert await repo.delete(digest) == 1
        else:
            assert isinstance(await repo.resolve_and_touch(digest), ResolvedSession)

        async def other():
            async with maker.begin() as db:
                other_repo = AuthSessionRepository(db, CONFIG)
                return (
                    await other_repo.resolve_and_touch(digest)
                    if delete_first
                    else await other_repo.delete(digest)
                )

        task = asyncio.create_task(other())
        try:
            await assert_waiting(task)
            await first.commit()
            result = await asyncio.wait_for(task, 5)
            assert result == (SessionRejection.UNKNOWN if delete_first else 1)
        finally:
            await first.rollback()
            if not task.done():
                task.cancel()
                await asyncio.gather(task, return_exceptions=True)
    async with maker.begin() as db:
        assert (
            await AuthSessionRepository(db, CONFIG).resolve_and_touch(digest)
            == SessionRejection.UNKNOWN
        )


@pytest.mark.parametrize("issue_first", [False, True])
async def test_account_lock_serializes_issuance_and_global_revoke(
    test_engine, issue_first
):
    maker, _ = await committed_seed(test_engine)
    async with maker() as first:
        repo = AuthSessionRepository(first, CONFIG)
        if issue_first:
            assert await repo.create(1, DIGEST) is not None
        else:
            assert await repo.delete_all(1) == 1

        async def other():
            async with maker.begin() as db:
                other_repo = AuthSessionRepository(db, CONFIG)
                return (
                    await other_repo.delete_all(1)
                    if issue_first
                    else await other_repo.create(1, DIGEST)
                )

        task = asyncio.create_task(other())
        try:
            await assert_waiting(task)
            await first.commit()
            result = await asyncio.wait_for(task, 5)
            assert result == 2 if issue_first else isinstance(result, AuthSession)
        finally:
            await first.rollback()
            if not task.done():
                task.cancel()
                await asyncio.gather(task, return_exceptions=True)
    async with maker.begin() as db:
        count = await db.scalar(select(func.count()).select_from(AuthSession))
        assert count == (0 if issue_first else 1)


async def test_pruners_skip_locked_batches_and_refresh(test_engine):
    maker, digests = await committed_seed(test_engine, 205)
    async with maker.begin() as db:
        await db.execute(
            update(AuthSession).values(
                last_seen_at=func.statement_timestamp() - timedelta(days=7)
            )
        )
    async with maker() as refresher, maker() as first, maker() as second:
        # A concurrent request has made one previously expired row active.
        await refresher.execute(
            update(AuthSession)
            .where(AuthSession.token_digest == digests[0])
            .values(last_seen_at=func.statement_timestamp())
        )
        assert await AuthSessionRepository(first, CONFIG).prune_expired() == 100
        assert await AuthSessionRepository(second, CONFIG).prune_expired() == 100
        await refresher.commit()
        await first.commit()
        await second.commit()
    async with maker.begin() as db:
        repo = AuthSessionRepository(db, CONFIG)
        assert await repo.prune_expired() == 4
        assert isinstance(await repo.resolve_and_touch(digests[0]), ResolvedSession)


async def test_creation_waits_for_account_deletion_without_fk_diagnostics(test_engine):
    maker, _ = await committed_seed(test_engine)
    async with maker() as deleting:
        await deleting.execute(delete(User).where(User.id == 1))

        async def issue():
            async with maker.begin() as db:
                return await AuthSessionRepository(db, CONFIG).create(1, DIGEST)

        task = asyncio.create_task(issue())
        try:
            await assert_waiting(task)
            await deleting.commit()
            assert await asyncio.wait_for(task, 5) is None
        finally:
            await deleting.rollback()
            if not task.done():
                task.cancel()
                await asyncio.gather(task, return_exceptions=True)


async def test_create_and_revoke_are_not_committed_by_repository(test_engine):
    maker, (digest,) = await committed_seed(test_engine)
    async with maker() as db:
        repo = AuthSessionRepository(db, CONFIG)
        assert await repo.create(1, DIGEST) is not None
        assert await repo.delete(digest) == 1
        await db.rollback()
    async with maker.begin() as db:
        repo = AuthSessionRepository(db, CONFIG)
        assert await repo.resolve_and_touch(DIGEST) == SessionRejection.UNKNOWN
        assert isinstance(await repo.resolve_and_touch(digest), ResolvedSession)


async def test_expiry_is_checked_after_waiting_for_an_unmodified_row(test_engine):
    maker = async_sessionmaker(test_engine, expire_on_commit=False)
    config = SessionConfig(idle_timeout_seconds=1, absolute_timeout_seconds=1)
    async with maker.begin() as db:
        db.add(User(id=1, github_username="learner"))
        await db.flush()
        await AuthSessionRepository(db, config).create(1, DIGEST)
    async with maker() as locker:
        await locker.execute(select(AuthSession).with_for_update())

        async def resolve():
            async with maker.begin() as db:
                return await AuthSessionRepository(db, config).resolve_and_touch(DIGEST)

        task = asyncio.create_task(resolve())
        try:
            await assert_waiting(task)
            await locker.execute(text("SELECT pg_sleep(1.05)"))
            await locker.commit()
            assert await asyncio.wait_for(task, 5) == SessionRejection.ABSOLUTE_EXPIRED
        finally:
            await locker.rollback()
            if not task.done():
                task.cancel()
                await asyncio.gather(task, return_exceptions=True)
