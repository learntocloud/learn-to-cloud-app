"""Integration tests for UserRepository."""

import asyncio

import pytest
from sqlalchemy import event, func, select
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from learn_to_cloud.models import User
from learn_to_cloud.repositories.user_repository import UserRepository

pytestmark = pytest.mark.integration


class TestUpsert:
    async def test_updates_existing_user(self, db_session: AsyncSession):
        repo = UserRepository(db_session)
        original = await repo.upsert(
            99999, display_name="Original", github_username="original"
        )
        created_at, updated_at = original.created_at, original.updated_at
        updated = await repo.upsert(
            99999,
            display_name="Updated",
            github_username="updated",
            avatar_url="https://example.com/new.png",
        )

        assert updated.id == 99999
        assert updated is original
        assert updated.display_name == "Updated"
        assert updated.github_username == "updated"
        assert updated.avatar_url == "https://example.com/new.png"
        assert updated.created_at == created_at
        assert updated.updated_at > updated_at
        assert updated.is_admin is False

    async def test_clears_name_and_avatar(self, db_session: AsyncSession):
        repo = UserRepository(db_session)
        user = await repo.upsert(
            99999,
            github_username="original",
            display_name="Original",
            avatar_url="avatar",
        )
        assert await repo.upsert(99999, github_username="original") is user
        assert user.display_name is None
        assert user.avatar_url is None
        await db_session.refresh(user)
        assert user.display_name is None
        assert user.avatar_url is None

    async def test_flushes_whole_session_before_provider_override(
        self, db_session: AsyncSession
    ):
        repo = UserRepository(db_session)
        user = await repo.upsert(
            99999, github_username="original", display_name="Original"
        )
        unrelated = User(id=99998, github_username="unrelated", display_name="Pending")
        db_session.add(unrelated)
        user.is_admin = True
        user.display_name = "Pending profile"
        user.github_username = "pending"
        user.avatar_url = "pending-avatar"

        flushed_profiles = []

        def record_flush(**event_args):
            session = event_args["session"]
            flushed_profiles.append(
                {
                    (row.id, row.display_name, row.github_username, row.avatar_url)
                    for row in (*session.new, *session.dirty)
                }
            )

        event.listen(db_session.sync_session, "after_flush", record_flush, named=True)
        try:
            returned = await repo.upsert(
                99999,
                github_username="provider",
                display_name="Provider",
                avatar_url="provider-avatar",
            )
        finally:
            event.remove(db_session.sync_session, "after_flush", record_flush)
        assert returned is user
        assert flushed_profiles == [
            {
                (99999, "Pending profile", "pending", "pending-avatar"),
                (99998, "Pending", "unrelated", None),
            }
        ]
        await db_session.refresh(user)
        await db_session.refresh(unrelated)
        assert user.is_admin is True
        assert (user.display_name, user.github_username, user.avatar_url) == (
            "Provider",
            "provider",
            "provider-avatar",
        )
        assert unrelated.display_name == "Pending"

    async def test_flushes_pending_insert_for_same_id(self, db_session: AsyncSession):
        pending = User(
            id=99999, github_username="pending", display_name="Pending", is_admin=True
        )
        db_session.add(pending)
        returned = await UserRepository(db_session).upsert(
            99999, github_username="provider", display_name="Provider"
        )
        assert returned is pending
        assert returned.display_name == "Provider"
        assert returned.is_admin is True
        await db_session.commit()
        assert await db_session.scalar(select(func.count()).select_from(User)) == 1

    async def test_caller_rollback_undoes_flush_and_upsert(
        self, test_engine: AsyncEngine
    ):
        async with AsyncSession(
            test_engine, autoflush=False, expire_on_commit=False
        ) as db:
            user = await UserRepository(db).upsert(
                99999, github_username="original", display_name="Original"
            )
            await db.commit()
            user.is_admin = True
            db.add(User(id=99998, github_username="pending"))
            await UserRepository(db).upsert(
                99999, github_username="changed", display_name=None
            )
            async with AsyncSession(test_engine) as observer:
                persisted = await observer.get(User, 99999)
                assert persisted is not None
                assert persisted.display_name == "Original"
                assert persisted.is_admin is False
                assert await observer.get(User, 99998) is None
            await db.rollback()
            await db.refresh(user)
            assert (user.display_name, user.github_username, user.is_admin) == (
                "Original",
                "original",
                False,
            )
            assert await db.get(User, 99998) is None

    async def test_concurrent_identity_is_unique(self, test_engine: AsyncEngine):
        barrier = asyncio.Barrier(2)

        async def write(name):
            async with AsyncSession(
                test_engine, autoflush=False, expire_on_commit=False
            ) as db:
                repo = UserRepository(db)
                await barrier.wait()
                user = await repo.upsert(99999, github_username=name, display_name=name)
                await db.commit()
                return user.id

        assert await asyncio.wait_for(
            asyncio.gather(write("one"), write("two")), timeout=10
        ) == [99999, 99999]
        async with AsyncSession(test_engine) as db:
            users = (await db.scalars(select(User))).all()
            assert len(users) == 1
            assert users[0].display_name in {"one", "two"}


class TestDelete:
    async def test_removes_user(self, db_session: AsyncSession):
        repo = UserRepository(db_session)
        await repo.upsert(33333, github_username="todelete")
        await db_session.flush()

        await repo.delete(33333)
        await db_session.flush()

        user = await db_session.scalar(select(User).where(User.id == 33333))
        assert user is None


class TestGetByIds:
    async def test_returns_matching_users(self, db_session: AsyncSession):
        repo = UserRepository(db_session)
        await repo.upsert(41001, github_username="ida")
        await repo.upsert(41002, github_username="idb")
        await db_session.flush()

        users = await repo.get_by_ids([41001, 41002, 99999999])
        ids = {u.id for u in users}
        assert ids == {41001, 41002}
