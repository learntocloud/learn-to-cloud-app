"""Integration tests for UserRepository."""

import asyncio
from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy import event, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from learn_to_cloud_shared.models import User
from learn_to_cloud_shared.repositories.user_repository import UserRepository

pytestmark = pytest.mark.integration


class TestGetOrCreate:
    async def test_creates_new_user(self, db_session: AsyncSession):
        repo = UserRepository(db_session)
        user = await repo.get_or_create(
            12345,
            display_name="Alice",
            github_username="alice",
            avatar_url="https://example.com/alice.png",
        )

        assert user.id == 12345
        assert user.display_name == "Alice"
        assert user.github_username == "alice"

    async def test_returns_existing_user_on_conflict(self, db_session: AsyncSession):
        repo = UserRepository(db_session)
        user1 = await repo.get_or_create(
            12345, display_name="Alice", github_username="alice"
        )
        user2 = await repo.get_or_create(
            12345, display_name="Bob", github_username="bob"
        )

        assert user1.id == user2.id
        # Should return the existing user, not overwrite
        assert user2 is user1
        assert user2.display_name == "Alice"
        assert user2.github_username == "alice"


class TestUpsert:
    async def test_creates_new_user(self, db_session: AsyncSession):
        repo = UserRepository(db_session)
        user = await repo.upsert(
            99999,
            display_name="New User",
            github_username="newuser",
        )

        assert user.id == 99999
        assert user.display_name == "New User"

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

        def record_flush(session, context):
            flushed_profiles.append(
                (user.display_name, user.github_username, user.avatar_url)
            )

        event.listen(db_session.sync_session, "after_flush", record_flush)
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
        assert flushed_profiles == [("Pending profile", "pending", "pending-avatar")]
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
        assert await UserRepository(db_session).count() == 1

    async def test_flush_failure_stops_before_upsert(self, test_engine: AsyncEngine):
        async with AsyncSession(test_engine, autoflush=False) as db:
            db.add(User(id=99998))
            with patch.object(db, "execute", wraps=db.execute) as execute:
                with pytest.raises(IntegrityError):
                    await UserRepository(db).upsert(99999, github_username="provider")
                execute.assert_not_awaited()
            await db.rollback()
            assert await UserRepository(db).count() == 0

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

    async def test_clean_session_upsert_is_one_statement(
        self, db_session: AsyncSession
    ):
        connection = await db_session.connection()
        statements = []

        def record(conn, cursor, statement, parameters, context, executemany):
            statements.append(statement.lower())

        event.listen(connection.sync_connection, "before_cursor_execute", record)
        try:
            repo = UserRepository(db_session)
            for name in ("First", "Updated", None):
                statements.clear()
                await repo.upsert(99999, github_username="profile", display_name=name)
                assert len(statements) == 1
                assert statements[0].startswith("insert into users")
                assert "on conflict (id) do update" in statements[0]
                assert "returning" in statements[0]
            statements.clear()
            await repo.get_or_create(99998, github_username="new", display_name="New")
            assert len(statements) == 2
            statements.clear()
            await repo.get_or_create(
                99998, github_username="ignored", display_name="Ignored"
            )
            assert len(statements) == 1
            assert statements[0].startswith("select ")
        finally:
            event.remove(connection.sync_connection, "before_cursor_execute", record)

    @pytest.mark.parametrize("operation", ["upsert", "get_or_create"])
    async def test_concurrent_identity_is_unique(
        self, test_engine: AsyncEngine, operation
    ):
        barrier = asyncio.Barrier(2)

        async def write(name):
            async with AsyncSession(
                test_engine, autoflush=False, expire_on_commit=False
            ) as db:
                repo = UserRepository(db)
                if operation == "get_or_create":
                    original_lookup = repo.get_by_id

                    async def synchronized_lookup(user_id):
                        result = await original_lookup(user_id)
                        await barrier.wait()
                        return result

                    with patch.object(
                        repo, "get_by_id", AsyncMock(side_effect=synchronized_lookup)
                    ):
                        user = await repo.get_or_create(
                            99999, github_username=name, display_name=name
                        )
                else:
                    await barrier.wait()
                    user = await repo.upsert(
                        99999, github_username=name, display_name=name
                    )
                await db.commit()
                return user.id

        assert await asyncio.wait_for(
            asyncio.gather(write("one"), write("two")), timeout=10
        ) == [99999, 99999]
        async with AsyncSession(test_engine) as db:
            users = (await db.scalars(select(User))).all()
            assert len(users) == 1
            assert users[0].display_name in {"one", "two"}


class TestGetById:
    async def test_returns_user(self, db_session: AsyncSession):
        repo = UserRepository(db_session)
        await repo.upsert(11111, display_name="Found", github_username="found")

        user = await repo.get_by_id(11111)
        assert user is not None
        assert user.display_name == "Found"

    async def test_returns_none_for_missing(self, db_session: AsyncSession):
        repo = UserRepository(db_session)
        user = await repo.get_by_id(99999999)
        assert user is None


class TestDelete:
    async def test_removes_user(self, db_session: AsyncSession):
        repo = UserRepository(db_session)
        await repo.upsert(33333, github_username="todelete")
        await db_session.flush()

        await repo.delete(33333)
        await db_session.flush()

        user = await repo.get_by_id(33333)
        assert user is None

    async def test_delete_nonexistent_is_noop(self, db_session: AsyncSession):
        """Deleting a non-existent user should not raise."""
        repo = UserRepository(db_session)
        await repo.delete(88888888)


class TestGetByIds:
    async def test_returns_matching_users(self, db_session: AsyncSession):
        repo = UserRepository(db_session)
        await repo.upsert(41001, github_username="ida")
        await repo.upsert(41002, github_username="idb")
        await db_session.flush()

        users = await repo.get_by_ids([41001, 41002, 99999999])
        ids = {u.id for u in users}
        assert ids == {41001, 41002}

    async def test_returns_empty_for_empty_input(self, db_session: AsyncSession):
        repo = UserRepository(db_session)
        assert await repo.get_by_ids([]) == []


class TestCount:
    async def test_counts_users(self, db_session: AsyncSession):
        repo = UserRepository(db_session)
        before = await repo.count()
        await repo.upsert(42001, github_username="counta")
        await repo.upsert(42002, github_username="countb")
        await db_session.flush()

        assert await repo.count() == before + 2
