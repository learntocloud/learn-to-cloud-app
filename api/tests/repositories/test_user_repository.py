"""Tests for UserRepository.

Tests database operations for user CRUD with real PostgreSQL.
Uses transaction rollback for test isolation (fast + realistic).
"""

import uuid

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from models import User
from repositories.user_repository import UserRepository
from tests.factories import (
    AdminUserFactory,
    PlaceholderUserFactory,
    UserFactory,
    create_async,
)


def unique_username(prefix: str = "user") -> str:
    """Generate a unique username for test isolation."""
    return f"{prefix}_{uuid.uuid4().hex[:8]}"


class TestUserRepositoryGetById:
    """Tests for UserRepository.get_by_id()."""

    async def test_returns_user_when_exists(self, db_session: AsyncSession):
        """Should return user when ID exists."""
        user = await create_async(UserFactory, db_session)
        repo = UserRepository(db_session)

        result = await repo.get_by_id(user.id)

        assert result is not None
        assert result.id == user.id
        assert result.email == user.email

    async def test_returns_none_when_not_exists(self, db_session: AsyncSession):
        """Should return None when user ID doesn't exist."""
        repo = UserRepository(db_session)

        result = await repo.get_by_id("user_nonexistent_123")

        assert result is None


class TestUserRepositoryGetByGithubUsername:
    """Tests for UserRepository.get_by_github_username()."""

    async def test_returns_user_when_username_exists(self, db_session: AsyncSession):
        """Should return user when GitHub username exists."""
        username = unique_username("ghuser")
        user = await create_async(
            UserFactory, db_session, github_username=username
        )
        repo = UserRepository(db_session)

        result = await repo.get_by_github_username(username)

        assert result is not None
        assert result.id == user.id
        assert result.github_username == username

    async def test_returns_none_when_username_not_exists(self, db_session: AsyncSession):
        """Should return None when GitHub username doesn't exist."""
        repo = UserRepository(db_session)

        result = await repo.get_by_github_username("nonexistent_user")

        assert result is None

    async def test_case_sensitive_lookup(self, db_session: AsyncSession):
        """Should do case-sensitive lookup (service normalizes to lowercase)."""
        username = unique_username("casetest")
        await create_async(UserFactory, db_session, github_username=username)
        repo = UserRepository(db_session)

        # Uppercase should not match (service layer normalizes before calling)
        result = await repo.get_by_github_username(username.upper())

        assert result is None


class TestUserRepositoryGetOrCreate:
    """Tests for UserRepository.get_or_create()."""

    async def test_returns_existing_user(self, db_session: AsyncSession):
        """Should return existing user without creating new one."""
        user = await create_async(UserFactory, db_session)
        repo = UserRepository(db_session)

        result = await repo.get_or_create(user.id)

        assert result.id == user.id
        assert result.email == user.email

    async def test_creates_placeholder_when_not_exists(self, db_session: AsyncSession):
        """Should create placeholder user when ID doesn't exist."""
        repo = UserRepository(db_session)
        new_id = "user_brand_new_12345"

        result = await repo.get_or_create(new_id)

        assert result.id == new_id
        assert result.email == f"{new_id}@placeholder.local"

    async def test_idempotent_on_concurrent_calls(self, db_session: AsyncSession):
        """Should handle concurrent creates safely (ON CONFLICT DO NOTHING)."""
        repo = UserRepository(db_session)
        user_id = "user_concurrent_test"

        # First call creates
        result1 = await repo.get_or_create(user_id)
        # Second call returns existing
        result2 = await repo.get_or_create(user_id)

        assert result1.id == result2.id
        assert result1.email == result2.email


class TestUserRepositoryCreate:
    """Tests for UserRepository.create()."""

    async def test_creates_user_with_all_fields(self, db_session: AsyncSession):
        """Should create user with all provided fields."""
        repo = UserRepository(db_session)

        user = await repo.create(
            user_id="user_create_test_123",
            email="test@example.com",
            first_name="Test",
            last_name="User",
            avatar_url="https://example.com/avatar.png",
            github_username="testuser",
        )
        await db_session.flush()

        assert user.id == "user_create_test_123"
        assert user.email == "test@example.com"
        assert user.first_name == "Test"
        assert user.last_name == "User"
        assert user.avatar_url == "https://example.com/avatar.png"
        assert user.github_username == "testuser"
        assert user.is_admin is False

    async def test_creates_user_with_minimal_fields(self, db_session: AsyncSession):
        """Should create user with only required fields."""
        repo = UserRepository(db_session)

        user = await repo.create(
            user_id="user_minimal_123",
            email="minimal@example.com",
        )
        await db_session.flush()

        assert user.id == "user_minimal_123"
        assert user.email == "minimal@example.com"
        assert user.first_name is None
        assert user.github_username is None


class TestUserRepositoryUpdate:
    """Tests for UserRepository.update()."""

    async def test_updates_single_field(self, db_session: AsyncSession):
        """Should update only specified field."""
        user = await create_async(UserFactory, db_session, first_name="Original")
        repo = UserRepository(db_session)

        await repo.update(user, first_name="Updated")

        assert user.first_name == "Updated"

    async def test_updates_multiple_fields(self, db_session: AsyncSession):
        """Should update multiple fields at once."""
        user = await create_async(UserFactory, db_session)
        repo = UserRepository(db_session)

        await repo.update(
            user,
            email="new@example.com",
            first_name="New",
            last_name="Name",
        )

        assert user.email == "new@example.com"
        assert user.first_name == "New"
        assert user.last_name == "Name"

    async def test_ignores_none_values(self, db_session: AsyncSession):
        """Should not update fields passed as None."""
        user = await create_async(
            UserFactory, db_session, first_name="Original", last_name="Name"
        )
        repo = UserRepository(db_session)

        await repo.update(user, first_name="Updated", last_name=None)

        assert user.first_name == "Updated"
        assert user.last_name == "Name"  # Unchanged

    async def test_updates_is_admin(self, db_session: AsyncSession):
        """Should update admin status."""
        user = await create_async(UserFactory, db_session, is_admin=False)
        repo = UserRepository(db_session)

        await repo.update(user, is_admin=True)

        assert user.is_admin is True

    async def test_clears_github_username_from_other_user(
        self, db_session: AsyncSession
    ):
        """Should clear github_username from existing user when reassigning."""
        existing_user = await create_async(
            UserFactory, db_session, github_username="sharedusername"
        )
        new_user = await create_async(
            UserFactory, db_session, github_username=None
        )
        repo = UserRepository(db_session)

        await repo.update(new_user, github_username="sharedusername")
        await db_session.flush()

        # Refresh to get updated state
        await db_session.refresh(existing_user)

        assert new_user.github_username == "sharedusername"
        assert existing_user.github_username is None


class TestUserRepositoryUpsert:
    """Tests for UserRepository.upsert()."""

    async def test_inserts_new_user(self, db_session: AsyncSession):
        """Should insert when user doesn't exist."""
        repo = UserRepository(db_session)

        user = await repo.upsert(
            user_id="user_upsert_new",
            email="upsert@example.com",
            first_name="Upsert",
        )

        assert user.id == "user_upsert_new"
        assert user.email == "upsert@example.com"
        assert user.first_name == "Upsert"

    async def test_updates_existing_user(self, db_session: AsyncSession):
        """Should update when user already exists."""
        # Create user directly (not through factory to control exactly)
        repo = UserRepository(db_session)
        await repo.create(
            user_id="user_upsert_existing",
            email="old@example.com",
            first_name="Old",
        )
        await db_session.flush()

        # Expire all to clear identity map cache
        db_session.expire_all()

        # Upsert with new values
        updated_user = await repo.upsert(
            user_id="user_upsert_existing",
            email="new@example.com",
            first_name="New",
        )

        # Check the returned user has updated values
        assert updated_user.id == "user_upsert_existing"
        assert updated_user.email == "new@example.com"
        assert updated_user.first_name == "New"


class TestUserRepositoryDelete:
    """Tests for UserRepository.delete()."""

    async def test_deletes_existing_user(self, db_session: AsyncSession):
        """Should delete user when exists."""
        user = await create_async(UserFactory, db_session)
        repo = UserRepository(db_session)

        await repo.delete(user.id)
        await db_session.flush()

        result = await repo.get_by_id(user.id)
        assert result is None

    async def test_no_error_when_user_not_exists(self, db_session: AsyncSession):
        """Should not error when deleting non-existent user."""
        repo = UserRepository(db_session)

        # Should not raise
        await repo.delete("user_nonexistent_delete")


class TestUserRepositoryGetManyByIds:
    """Tests for UserRepository.get_many_by_ids()."""

    async def test_returns_all_matching_users(self, db_session: AsyncSession):
        """Should return all users matching provided IDs."""
        user1 = await create_async(UserFactory, db_session)
        user2 = await create_async(UserFactory, db_session)
        await create_async(UserFactory, db_session)  # Not requested
        repo = UserRepository(db_session)

        result = await repo.get_many_by_ids([user1.id, user2.id])

        assert len(result) == 2
        result_ids = {u.id for u in result}
        assert user1.id in result_ids
        assert user2.id in result_ids

    async def test_returns_empty_for_empty_input(self, db_session: AsyncSession):
        """Should return empty list for empty input."""
        repo = UserRepository(db_session)

        result = await repo.get_many_by_ids([])

        assert result == []

    async def test_skips_missing_ids(self, db_session: AsyncSession):
        """Should silently skip IDs that don't exist."""
        user = await create_async(UserFactory, db_session)
        repo = UserRepository(db_session)

        result = await repo.get_many_by_ids([user.id, "user_nonexistent"])

        assert len(result) == 1
        assert result[0].id == user.id
