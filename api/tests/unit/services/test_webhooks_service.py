"""Unit tests for services/webhooks_service.py.

Tests Clerk webhook event handling for user sync.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from services.webhooks_service import (
    handle_clerk_event,
    handle_user_created,
    handle_user_deleted,
    handle_user_updated,
)


class TestHandleUserCreated:
    """Test handle_user_created function."""

    @pytest.fixture
    def mock_db(self):
        return MagicMock()

    @pytest.mark.asyncio
    async def test_creates_user_with_full_data(self, mock_db):
        """Creates user with all available data from webhook."""
        data = {
            "id": "user-123",
            "first_name": "John",
            "last_name": "Doe",
            "image_url": "https://example.com/avatar.png",
            "primary_email_address_id": "email-1",
            "email_addresses": [{"id": "email-1", "email_address": "john@example.com"}],
            "external_accounts": [{"provider": "github", "username": "JohnDoe"}],
        }

        with patch("services.webhooks_service.UserRepository") as MockRepo:
            repo_instance = AsyncMock()
            MockRepo.return_value = repo_instance

            await handle_user_created(mock_db, data)

        repo_instance.upsert.assert_called_once()
        call_kwargs = repo_instance.upsert.call_args.kwargs
        assert call_kwargs["user_id"] == "user-123"
        assert call_kwargs["email"] == "john@example.com"
        assert call_kwargs["first_name"] == "John"
        assert call_kwargs["github_username"] == "johndoe"  # Normalized to lowercase

    @pytest.mark.asyncio
    async def test_ignores_missing_user_id(self, mock_db):
        """Returns early if no user ID in data."""
        data = {"first_name": "John"}  # No id field

        with patch("services.webhooks_service.UserRepository") as MockRepo:
            repo_instance = AsyncMock()
            MockRepo.return_value = repo_instance

            await handle_user_created(mock_db, data)

        repo_instance.upsert.assert_not_called()

    @pytest.mark.asyncio
    async def test_uses_fallback_email(self, mock_db):
        """Uses fallback email when no primary email available."""
        data = {
            "id": "user-456",
            "email_addresses": [],  # No emails
        }

        with patch("services.webhooks_service.UserRepository") as MockRepo:
            repo_instance = AsyncMock()
            MockRepo.return_value = repo_instance

            await handle_user_created(mock_db, data)

        call_kwargs = repo_instance.upsert.call_args.kwargs
        assert call_kwargs["email"] == "user-456@unknown.local"


class TestHandleUserUpdated:
    """Test handle_user_updated function."""

    @pytest.fixture
    def mock_db(self):
        return MagicMock()

    @pytest.mark.asyncio
    async def test_updates_existing_user(self, mock_db):
        """Updates existing user with new data."""
        existing_user = MagicMock()
        existing_user.email = "old@example.com"

        data = {
            "id": "user-123",
            "first_name": "Jane",
            "last_name": "Smith",
            "image_url": "https://example.com/new-avatar.png",
            "primary_email_address_id": "email-1",
            "email_addresses": [{"id": "email-1", "email_address": "jane@example.com"}],
            "external_accounts": [{"provider": "github", "username": "JaneSmith"}],
        }

        with patch("services.webhooks_service.UserRepository") as MockRepo:
            repo_instance = AsyncMock()
            repo_instance.get_by_id.return_value = existing_user
            MockRepo.return_value = repo_instance

            await handle_user_updated(mock_db, data)

        call_kwargs = repo_instance.upsert.call_args.kwargs
        assert call_kwargs["email"] == "jane@example.com"
        assert call_kwargs["first_name"] == "Jane"
        assert call_kwargs["github_username"] == "janesmith"

    @pytest.mark.asyncio
    async def test_creates_new_user_if_not_found(self, mock_db):
        """Creates user if not found (upsert behavior)."""
        data = {
            "id": "new-user",
            "first_name": "New",
            "last_name": "User",
        }

        with patch("services.webhooks_service.UserRepository") as MockRepo:
            repo_instance = AsyncMock()
            repo_instance.get_by_id.return_value = None  # User doesn't exist
            MockRepo.return_value = repo_instance

            await handle_user_updated(mock_db, data)

        repo_instance.upsert.assert_called_once()

    @pytest.mark.asyncio
    async def test_ignores_missing_user_id(self, mock_db):
        """Returns early if no user ID in data."""
        data = {"first_name": "John"}

        with patch("services.webhooks_service.UserRepository") as MockRepo:
            repo_instance = AsyncMock()
            MockRepo.return_value = repo_instance

            await handle_user_updated(mock_db, data)

        repo_instance.get_by_id.assert_not_called()
        repo_instance.upsert.assert_not_called()


class TestHandleUserDeleted:
    """Test handle_user_deleted function."""

    @pytest.fixture
    def mock_db(self):
        return MagicMock()

    @pytest.mark.asyncio
    async def test_deletes_user(self, mock_db):
        """Deletes user by ID."""
        data = {"id": "user-to-delete"}

        with patch("services.webhooks_service.UserRepository") as MockRepo:
            repo_instance = AsyncMock()
            MockRepo.return_value = repo_instance

            await handle_user_deleted(mock_db, data)

        repo_instance.delete.assert_called_once_with("user-to-delete")

    @pytest.mark.asyncio
    async def test_ignores_missing_user_id(self, mock_db):
        """Returns early if no user ID in data."""
        data = {}

        with patch("services.webhooks_service.UserRepository") as MockRepo:
            repo_instance = AsyncMock()
            MockRepo.return_value = repo_instance

            await handle_user_deleted(mock_db, data)

        repo_instance.delete.assert_not_called()


class TestHandleClerkEvent:
    """Test handle_clerk_event function."""

    @pytest.fixture
    def mock_db(self):
        return MagicMock()

    @pytest.mark.asyncio
    async def test_returns_already_processed_for_duplicate(self, mock_db):
        """Returns 'already_processed' for duplicate svix_id."""
        with patch(
            "services.webhooks_service.ProcessedWebhookRepository"
        ) as MockWebhook:
            webhook_repo = AsyncMock()
            webhook_repo.try_mark_processed.return_value = False  # Already seen
            MockWebhook.return_value = webhook_repo

            result = await handle_clerk_event(
                mock_db,
                svix_id="duplicate-id",
                event_type="user.created",
                data={"id": "user-123"},
            )

        assert result == "already_processed"

    @pytest.mark.asyncio
    async def test_handles_user_created_event(self, mock_db):
        """Handles user.created event type."""
        with (
            patch(
                "services.webhooks_service.ProcessedWebhookRepository"
            ) as MockWebhook,
            patch("services.webhooks_service.handle_user_created") as mock_handle,
        ):
            webhook_repo = AsyncMock()
            webhook_repo.try_mark_processed.return_value = True  # First time
            MockWebhook.return_value = webhook_repo

            result = await handle_clerk_event(
                mock_db,
                svix_id="new-id-1",
                event_type="user.created",
                data={"id": "user-123"},
            )

        assert result == "processed"
        mock_handle.assert_called_once_with(mock_db, {"id": "user-123"})

    @pytest.mark.asyncio
    async def test_handles_user_updated_event(self, mock_db):
        """Handles user.updated event type."""
        with (
            patch(
                "services.webhooks_service.ProcessedWebhookRepository"
            ) as MockWebhook,
            patch("services.webhooks_service.handle_user_updated") as mock_handle,
        ):
            webhook_repo = AsyncMock()
            webhook_repo.try_mark_processed.return_value = True
            MockWebhook.return_value = webhook_repo

            result = await handle_clerk_event(
                mock_db,
                svix_id="new-id-2",
                event_type="user.updated",
                data={"id": "user-456"},
            )

        assert result == "processed"
        mock_handle.assert_called_once_with(mock_db, {"id": "user-456"})

    @pytest.mark.asyncio
    async def test_handles_user_deleted_event(self, mock_db):
        """Handles user.deleted event type."""
        with (
            patch(
                "services.webhooks_service.ProcessedWebhookRepository"
            ) as MockWebhook,
            patch("services.webhooks_service.handle_user_deleted") as mock_handle,
        ):
            webhook_repo = AsyncMock()
            webhook_repo.try_mark_processed.return_value = True
            MockWebhook.return_value = webhook_repo

            result = await handle_clerk_event(
                mock_db,
                svix_id="new-id-3",
                event_type="user.deleted",
                data={"id": "user-789"},
            )

        assert result == "processed"
        mock_handle.assert_called_once_with(mock_db, {"id": "user-789"})

    @pytest.mark.asyncio
    async def test_ignores_unknown_event_type(self, mock_db):
        """Unknown event types are ignored (no handler called)."""
        with (
            patch(
                "services.webhooks_service.ProcessedWebhookRepository"
            ) as MockWebhook,
            patch("services.webhooks_service.handle_user_created") as mock_created,
            patch("services.webhooks_service.handle_user_updated") as mock_updated,
            patch("services.webhooks_service.handle_user_deleted") as mock_deleted,
        ):
            webhook_repo = AsyncMock()
            webhook_repo.try_mark_processed.return_value = True
            MockWebhook.return_value = webhook_repo

            result = await handle_clerk_event(
                mock_db,
                svix_id="new-id-4",
                event_type="session.created",  # Not handled
                data={"session_id": "sess-123"},
            )

        assert result == "processed"
        mock_created.assert_not_called()
        mock_updated.assert_not_called()
        mock_deleted.assert_not_called()
