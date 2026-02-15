"""Integration tests for UserRepository."""

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from repositories.user_repository import UserRepository

pytestmark = pytest.mark.integration


class TestGetOrCreate:
    async def test_creates_new_user(self, db_session: AsyncSession):
        repo = UserRepository(db_session)
        user = await repo.get_or_create(
            12345,
            first_name="Alice",
            github_username="alice",
            avatar_url="https://example.com/alice.png",
        )

        assert user.id == 12345
        assert user.first_name == "Alice"
        assert user.github_username == "alice"

    async def test_returns_existing_user_on_conflict(self, db_session: AsyncSession):
        repo = UserRepository(db_session)
        user1 = await repo.get_or_create(
            12345, first_name="Alice", github_username="alice"
        )
        user2 = await repo.get_or_create(12345, first_name="Bob", github_username="bob")

        assert user1.id == user2.id
        # Should return the existing user, not overwrite
        assert user2.first_name == "Alice"


class TestUpsert:
    async def test_creates_new_user(self, db_session: AsyncSession):
        repo = UserRepository(db_session)
        user = await repo.upsert(
            99999,
            first_name="New",
            last_name="User",
            github_username="newuser",
        )

        assert user.id == 99999
        assert user.first_name == "New"
        assert user.last_name == "User"

    async def test_updates_existing_user(self, db_session: AsyncSession):
        repo = UserRepository(db_session)
        await repo.upsert(99999, first_name="Original", github_username="original")
        updated = await repo.upsert(
            99999, first_name="Updated", github_username="updated"
        )

        assert updated.id == 99999
        assert updated.first_name == "Updated"
        assert updated.github_username == "updated"


class TestGetById:
    async def test_returns_user(self, db_session: AsyncSession):
        repo = UserRepository(db_session)
        await repo.upsert(11111, first_name="Found", github_username="found")

        user = await repo.get_by_id(11111)
        assert user is not None
        assert user.first_name == "Found"

    async def test_returns_none_for_missing(self, db_session: AsyncSession):
        repo = UserRepository(db_session)
        user = await repo.get_by_id(99999999)
        assert user is None


class TestGetByGithubUsername:
    async def test_returns_user(self, db_session: AsyncSession):
        repo = UserRepository(db_session)
        await repo.upsert(22222, github_username="testuser")

        user = await repo.get_by_github_username("testuser")
        assert user is not None
        assert user.id == 22222

    async def test_returns_none_for_missing(self, db_session: AsyncSession):
        repo = UserRepository(db_session)
        user = await repo.get_by_github_username("nonexistent")
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
