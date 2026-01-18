"""Integration tests for repositories/user_repository.py.

Uses real PostgreSQL database with transaction rollback for isolation.
"""

import pytest

from models import User
from repositories.user_repository import UserRepository


@pytest.mark.asyncio
class TestUserRepositoryIntegration:
    """Integration tests for UserRepository."""

    async def test_get_by_id_returns_user(self, db_session):
        """get_by_id returns existing user."""
        user = User(
            id="test-user",
            email="test@example.com",
            first_name="Test",
            last_name="User",
        )
        db_session.add(user)
        await db_session.flush()

        repo = UserRepository(db_session)
        result = await repo.get_by_id("test-user")

        assert result is not None
        assert result.id == "test-user"
        assert result.email == "test@example.com"

    async def test_get_by_id_returns_none_for_missing(self, db_session):
        """get_by_id returns None for non-existent user."""
        repo = UserRepository(db_session)
        result = await repo.get_by_id("nonexistent")
        assert result is None

    async def test_get_by_github_username(self, db_session):
        """get_by_github_username finds user by GitHub username."""
        user = User(
            id="test-user",
            email="test@example.com",
            github_username="testuser",
        )
        db_session.add(user)
        await db_session.flush()

        repo = UserRepository(db_session)
        result = await repo.get_by_github_username("testuser")

        assert result is not None
        assert result.github_username == "testuser"

    async def test_get_by_github_username_returns_none(self, db_session):
        """get_by_github_username returns None if not found."""
        repo = UserRepository(db_session)
        result = await repo.get_by_github_username("nonexistent")
        assert result is None

    async def test_get_or_create_returns_existing(self, db_session):
        """get_or_create returns existing user if present."""
        user = User(
            id="existing-user",
            email="existing@example.com",
            first_name="Existing",
        )
        db_session.add(user)
        await db_session.flush()

        repo = UserRepository(db_session)
        result = await repo.get_or_create("existing-user")

        assert result.id == "existing-user"
        assert result.email == "existing@example.com"
        assert result.first_name == "Existing"

    async def test_get_or_create_creates_placeholder(self, db_session):
        """get_or_create creates placeholder user if not exists."""
        repo = UserRepository(db_session)
        result = await repo.get_or_create("new-user")

        assert result.id == "new-user"
        assert result.email == "new-user@placeholder.local"

    async def test_upsert_creates_new_user(self, db_session):
        """upsert creates user if not exists."""
        repo = UserRepository(db_session)

        result = await repo.upsert(
            user_id="new-user",
            email="new@example.com",
            first_name="New",
            last_name="User",
            avatar_url="https://example.com/avatar.png",
            github_username="newuser",
        )

        assert result.id == "new-user"
        assert result.email == "new@example.com"
        assert result.github_username == "newuser"

    async def test_upsert_updates_existing_user(self, db_session):
        """upsert updates existing user.

        Note: PostgreSQL upsert returns the updated row via RETURNING clause,
        but SQLAlchemy's identity map may cache the old object. We use a fresh
        session for the upsert to avoid identity map issues.
        """
        # Insert user in one transaction
        user = User(
            id="existing-user",
            email="old@example.com",
            first_name="Old",
        )
        db_session.add(user)
        await db_session.commit()

        # Clear session to avoid identity map caching
        db_session.expire_all()

        repo = UserRepository(db_session)
        await repo.upsert(
            user_id="existing-user",
            email="updated@example.com",
            first_name="Updated",
            last_name="Name",
        )

        # Verify by fetching fresh from database
        db_session.expire_all()
        from sqlalchemy import select

        stmt = select(User).where(User.id == "existing-user")
        res = await db_session.execute(stmt)
        fetched = res.scalar_one()

        assert fetched.email == "updated@example.com"
        assert fetched.first_name == "Updated"

    async def test_create_user(self, db_session):
        """create creates a new user."""
        repo = UserRepository(db_session)

        user = await repo.create(
            user_id="created-user",
            email="created@example.com",
            first_name="Created",
            last_name="User",
            github_username="createduser",
        )
        await db_session.flush()

        assert user.id == "created-user"
        assert user.email == "created@example.com"

    async def test_update_user_fields(self, db_session):
        """update modifies specified fields only."""
        user = User(
            id="update-user",
            email="original@example.com",
            first_name="Original",
            last_name="Name",
        )
        db_session.add(user)
        await db_session.flush()

        repo = UserRepository(db_session)
        updated = await repo.update(
            user,
            first_name="Updated",
            avatar_url="https://new-avatar.com/img.png",
        )

        assert updated.first_name == "Updated"
        assert updated.avatar_url == "https://new-avatar.com/img.png"
        # Unchanged fields
        assert updated.email == "original@example.com"
        assert updated.last_name == "Name"

    async def test_update_clears_duplicate_github_username(self, db_session):
        """update clears github_username from other user if duplicate."""
        old_user = User(
            id="old-user",
            email="old@example.com",
            github_username="shared",
        )
        new_user = User(
            id="new-user",
            email="new@example.com",
            github_username=None,
        )
        db_session.add(old_user)
        db_session.add(new_user)
        await db_session.flush()

        repo = UserRepository(db_session)
        await repo.update(new_user, github_username="shared")

        # Old user should have github_username cleared
        refreshed_old = await repo.get_by_id("old-user")
        assert refreshed_old is not None
        assert refreshed_old.github_username is None
        # New user should have it
        assert new_user.github_username == "shared"

    async def test_delete_user(self, db_session):
        """delete removes user from database."""
        user = User(
            id="delete-me",
            email="delete@example.com",
        )
        db_session.add(user)
        await db_session.flush()

        repo = UserRepository(db_session)
        await repo.delete("delete-me")
        await db_session.flush()

        result = await repo.get_by_id("delete-me")
        assert result is None

    async def test_get_many_by_ids(self, db_session):
        """get_many_by_ids returns multiple users."""
        user1 = User(id="user-1", email="user1@example.com")
        user2 = User(id="user-2", email="user2@example.com")
        user3 = User(id="user-3", email="user3@example.com")
        db_session.add_all([user1, user2, user3])
        await db_session.flush()

        repo = UserRepository(db_session)
        results = await repo.get_many_by_ids(["user-1", "user-3"])

        assert len(results) == 2
        ids = {u.id for u in results}
        assert ids == {"user-1", "user-3"}

    async def test_get_many_by_ids_empty_list(self, db_session):
        """get_many_by_ids returns empty list for empty input."""
        repo = UserRepository(db_session)
        results = await repo.get_many_by_ids([])
        assert results == []

    async def test_get_many_by_ids_skips_missing(self, db_session):
        """get_many_by_ids silently skips non-existent IDs."""
        user = User(id="existing", email="existing@example.com")
        db_session.add(user)
        await db_session.flush()

        repo = UserRepository(db_session)
        results = await repo.get_many_by_ids(["existing", "nonexistent"])

        assert len(results) == 1
        assert results[0].id == "existing"
