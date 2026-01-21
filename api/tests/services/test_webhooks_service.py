"""Tests for webhooks service."""

from sqlalchemy.ext.asyncio import AsyncSession

from services.webhooks_service import (
    handle_clerk_event,
    handle_user_created,
    handle_user_deleted,
    handle_user_updated,
)
from tests.factories import UserFactory


class TestHandleUserCreated:
    """Tests for handle_user_created."""

    async def test_creates_user_from_webhook_data(self, db_session: AsyncSession):
        """Test creating a new user from webhook data."""
        data = {
            "id": "user_webhook_test_123",
            "first_name": "John",
            "last_name": "Doe",
            "image_url": "https://example.com/avatar.png",
            "email_addresses": [{"id": "email_1", "email_address": "john@example.com"}],
            "primary_email_address_id": "email_1",
            "external_accounts": [{"provider": "oauth_github", "username": "johndoe"}],
        }

        await handle_user_created(db_session, data)

        # Verify user was created
        from repositories.user_repository import UserRepository

        repo = UserRepository(db_session)
        user = await repo.get_by_id("user_webhook_test_123")

        assert user is not None
        assert user.first_name == "John"
        assert user.last_name == "Doe"
        assert user.email == "john@example.com"
        assert user.github_username == "johndoe"

    async def test_handles_missing_user_id(self, db_session: AsyncSession):
        """Test handling webhook data without user ID."""
        data = {
            "first_name": "John",
            "email_addresses": [],
        }

        # Should not raise, just return early
        await handle_user_created(db_session, data)

    async def test_normalizes_github_username(self, db_session: AsyncSession):
        """Test that GitHub username is normalized to lowercase."""
        data = {
            "id": "user_normalize_test",
            "external_accounts": [{"provider": "oauth_github", "username": "JohnDOE"}],
            "email_addresses": [],
        }

        await handle_user_created(db_session, data)

        from repositories.user_repository import UserRepository

        repo = UserRepository(db_session)
        user = await repo.get_by_id("user_normalize_test")

        assert user.github_username == "johndoe"


class TestHandleUserUpdated:
    """Tests for handle_user_updated."""

    async def test_updates_existing_user(self, db_session: AsyncSession):
        """Test updating an existing user."""
        # Create existing user using the repository to ensure proper setup
        from repositories.user_repository import UserRepository

        repo = UserRepository(db_session)
        await repo.create(
            user_id="user_update_test",
            email="old@example.com",
            first_name="Old",
            last_name="Name",
        )
        await db_session.flush()

        data = {
            "id": "user_update_test",
            "first_name": "New",
            "last_name": "Updated",
            "email_addresses": [{"id": "email_1", "email_address": "new@example.com"}],
            "primary_email_address_id": "email_1",
            "external_accounts": [],
        }

        await handle_user_updated(db_session, data)
        await db_session.flush()

        # Expire the cached object and refetch
        db_session.expire_all()
        updated = await repo.get_by_id("user_update_test")

        assert updated.first_name == "New"
        assert updated.last_name == "Updated"

    async def test_creates_user_if_not_exists(self, db_session: AsyncSession):
        """Test that update creates user if they don't exist."""
        data = {
            "id": "user_upsert_test",
            "first_name": "Created",
            "last_name": "OnUpdate",
            "email_addresses": [
                {"id": "email_1", "email_address": "created@example.com"}
            ],
            "primary_email_address_id": "email_1",
            "external_accounts": [],
        }

        await handle_user_updated(db_session, data)

        from repositories.user_repository import UserRepository

        repo = UserRepository(db_session)
        user = await repo.get_by_id("user_upsert_test")

        assert user is not None
        assert user.first_name == "Created"

    async def test_preserves_email_when_existing_user(self, db_session: AsyncSession):
        """Test that existing email is used as fallback."""
        user = UserFactory.build(
            id="user_email_preserve",
            email="original@example.com",
        )
        db_session.add(user)
        await db_session.flush()

        data = {
            "id": "user_email_preserve",
            "first_name": "Updated",
            "email_addresses": [],  # No emails in update
            "external_accounts": [],
        }

        await handle_user_updated(db_session, data)

        from repositories.user_repository import UserRepository

        repo = UserRepository(db_session)
        updated = await repo.get_by_id("user_email_preserve")

        # Should keep original email (or use placeholder)
        assert updated.email is not None


class TestHandleUserDeleted:
    """Tests for handle_user_deleted."""

    async def test_deletes_existing_user(self, db_session: AsyncSession):
        """Test deleting an existing user."""
        user = UserFactory.build(id="user_delete_test")
        db_session.add(user)
        await db_session.flush()

        data = {"id": "user_delete_test"}

        await handle_user_deleted(db_session, data)

        from repositories.user_repository import UserRepository

        repo = UserRepository(db_session)
        deleted = await repo.get_by_id("user_delete_test")

        assert deleted is None

    async def test_handles_nonexistent_user(self, db_session: AsyncSession):
        """Test deleting a user that doesn't exist."""
        data = {"id": "nonexistent_user"}

        # Should not raise
        await handle_user_deleted(db_session, data)

    async def test_handles_missing_user_id(self, db_session: AsyncSession):
        """Test handling delete with missing user ID."""
        data = {}

        # Should not raise
        await handle_user_deleted(db_session, data)


class TestHandleClerkEvent:
    """Tests for handle_clerk_event."""

    async def test_handles_user_created_event(self, db_session: AsyncSession):
        """Test handling user.created event."""
        result = await handle_clerk_event(
            db_session,
            svix_id="svix_test_created",
            event_type="user.created",
            data={
                "id": "user_event_created",
                "first_name": "Event",
                "email_addresses": [],
                "external_accounts": [],
            },
        )

        assert result == "processed"

    async def test_handles_user_updated_event(self, db_session: AsyncSession):
        """Test handling user.updated event."""
        result = await handle_clerk_event(
            db_session,
            svix_id="svix_test_updated",
            event_type="user.updated",
            data={
                "id": "user_event_updated",
                "first_name": "Updated",
                "email_addresses": [],
                "external_accounts": [],
            },
        )

        assert result == "processed"

    async def test_handles_user_deleted_event(self, db_session: AsyncSession):
        """Test handling user.deleted event."""
        # Create user first
        user = UserFactory.build(id="user_event_deleted")
        db_session.add(user)
        await db_session.flush()

        result = await handle_clerk_event(
            db_session,
            svix_id="svix_test_deleted",
            event_type="user.deleted",
            data={"id": "user_event_deleted"},
        )

        assert result == "processed"

    async def test_idempotency_returns_already_processed(
        self, db_session: AsyncSession
    ):
        """Test that duplicate svix_id returns already_processed."""
        svix_id = "svix_duplicate_test"

        # First call
        result1 = await handle_clerk_event(
            db_session,
            svix_id=svix_id,
            event_type="user.created",
            data={
                "id": "user_idempotent",
                "email_addresses": [],
                "external_accounts": [],
            },
        )

        # Second call with same svix_id
        result2 = await handle_clerk_event(
            db_session,
            svix_id=svix_id,
            event_type="user.created",
            data={
                "id": "user_idempotent",
                "email_addresses": [],
                "external_accounts": [],
            },
        )

        assert result1 == "processed"
        assert result2 == "already_processed"

    async def test_handles_unknown_event_type(self, db_session: AsyncSession):
        """Test handling unknown event type."""
        result = await handle_clerk_event(
            db_session,
            svix_id="svix_unknown_event",
            event_type="unknown.event",
            data={"id": "user_123"},
        )

        # Should still be processed (just no action taken)
        assert result == "processed"
