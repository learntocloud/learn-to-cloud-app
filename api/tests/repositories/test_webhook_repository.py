"""Tests for webhook repository."""

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

# Mark all tests in this module as integration tests (database required)
pytestmark = pytest.mark.integration

from models import ProcessedWebhook
from repositories.webhook_repository import ProcessedWebhookRepository


class TestProcessedWebhookRepository:
    """Tests for ProcessedWebhookRepository."""

    async def test_try_mark_processed_first_time(self, db_session: AsyncSession):
        """Test marking a webhook as processed for the first time."""
        repo = ProcessedWebhookRepository(db_session)
        result = await repo.try_mark_processed("svix-id-123", "user.created")
        assert result is True

    async def test_try_mark_processed_duplicate(self, db_session: AsyncSession):
        """Test marking the same webhook as processed twice."""
        repo = ProcessedWebhookRepository(db_session)

        # First time should succeed
        result1 = await repo.try_mark_processed("svix-id-456", "user.created")
        assert result1 is True

        # Second time should return False (already processed)
        result2 = await repo.try_mark_processed("svix-id-456", "user.created")
        assert result2 is False

    async def test_try_mark_processed_different_ids(self, db_session: AsyncSession):
        """Test marking different webhooks as processed."""
        repo = ProcessedWebhookRepository(db_session)

        result1 = await repo.try_mark_processed("svix-id-aaa", "user.created")
        result2 = await repo.try_mark_processed("svix-id-bbb", "user.updated")

        assert result1 is True
        assert result2 is True

    async def test_try_mark_processed_preserves_session(self, db_session: AsyncSession):
        """Test that IntegrityError doesn't invalidate the session."""
        repo = ProcessedWebhookRepository(db_session)

        # Mark as processed
        await repo.try_mark_processed("svix-id-xyz", "user.created")

        # Try duplicate - should handle gracefully
        result = await repo.try_mark_processed("svix-id-xyz", "user.created")
        assert result is False

        # Session should still be usable
        result2 = await repo.try_mark_processed("svix-id-new", "user.deleted")
        assert result2 is True

    async def test_delete_older_than_deletes_old_records(
        self, db_session: AsyncSession
    ):
        """Test deleting records older than specified days."""
        repo = ProcessedWebhookRepository(db_session)

        # Create an old record (manually set processed_at)
        old_webhook = ProcessedWebhook(
            id="old-webhook-id",
            event_type="user.created",
        )
        db_session.add(old_webhook)
        await db_session.flush()

        # Manually update the timestamp to be old
        old_time = datetime.now(UTC) - timedelta(days=10)
        old_webhook.processed_at = old_time
        await db_session.flush()

        # Create a recent record
        await repo.try_mark_processed("recent-webhook-id", "user.updated")

        # Delete records older than 7 days
        deleted_count = await repo.delete_older_than(days=7)

        assert deleted_count == 1

    async def test_delete_older_than_keeps_recent_records(
        self, db_session: AsyncSession
    ):
        """Test that recent records are not deleted."""
        repo = ProcessedWebhookRepository(db_session)

        # Create recent records
        await repo.try_mark_processed("recent-1", "user.created")
        await repo.try_mark_processed("recent-2", "user.updated")

        # Delete records older than 7 days
        deleted_count = await repo.delete_older_than(days=7)

        assert deleted_count == 0

    async def test_delete_older_than_with_custom_days(self, db_session: AsyncSession):
        """Test delete_older_than with custom days parameter."""
        repo = ProcessedWebhookRepository(db_session)

        # Create a record that's 3 days old
        webhook = ProcessedWebhook(
            id="three-day-old",
            event_type="user.created",
        )
        db_session.add(webhook)
        await db_session.flush()

        webhook.processed_at = datetime.now(UTC) - timedelta(days=3)
        await db_session.flush()

        # Should not delete with 7 days
        deleted = await repo.delete_older_than(days=7)
        assert deleted == 0

        # Should delete with 2 days
        deleted = await repo.delete_older_than(days=2)
        assert deleted == 1

    async def test_delete_older_than_returns_zero_on_empty(
        self, db_session: AsyncSession
    ):
        """Test delete_older_than returns 0 when no records exist."""
        repo = ProcessedWebhookRepository(db_session)
        deleted_count = await repo.delete_older_than(days=7)
        assert deleted_count == 0
