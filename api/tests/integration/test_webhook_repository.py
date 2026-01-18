"""Integration tests for repositories/webhook_repository.py.

Uses real PostgreSQL database with transaction rollback for isolation.
"""

from datetime import UTC, datetime, timedelta

import pytest

from models import ProcessedWebhook
from repositories.webhook_repository import ProcessedWebhookRepository


@pytest.mark.asyncio
class TestWebhookRepositoryIntegration:
    """Integration tests for ProcessedWebhookRepository."""

    async def test_try_mark_processed_returns_true_first_time(self, db_session):
        """try_mark_processed returns True for new webhook."""
        repo = ProcessedWebhookRepository(db_session)
        result = await repo.try_mark_processed("svix_123", "user.created")

        assert result is True

    async def test_try_mark_processed_returns_false_duplicate(self, db_session):
        """try_mark_processed returns False for duplicate webhook."""
        repo = ProcessedWebhookRepository(db_session)

        # First time should succeed
        first_result = await repo.try_mark_processed("svix_456", "user.created")
        assert first_result is True

        # Commit to ensure it's persisted
        await db_session.commit()

        # Second time should return False
        second_result = await repo.try_mark_processed("svix_456", "user.created")
        assert second_result is False

    async def test_delete_older_than_removes_old_webhooks(self, db_session):
        """delete_older_than removes webhooks older than specified days."""
        # Create an old webhook (10 days ago)
        old_webhook = ProcessedWebhook(
            id="old_svix",
            event_type="user.created",
            processed_at=datetime.now(UTC) - timedelta(days=10),
        )
        db_session.add(old_webhook)

        # Create a recent webhook (1 day ago)
        recent_webhook = ProcessedWebhook(
            id="recent_svix",
            event_type="user.updated",
            processed_at=datetime.now(UTC) - timedelta(days=1),
        )
        db_session.add(recent_webhook)
        await db_session.flush()

        repo = ProcessedWebhookRepository(db_session)
        deleted_count = await repo.delete_older_than(days=7)

        assert deleted_count == 1

    async def test_delete_older_than_keeps_recent_webhooks(self, db_session):
        """delete_older_than keeps webhooks newer than cutoff."""
        # Create recent webhooks
        for i in range(3):
            webhook = ProcessedWebhook(
                id=f"recent_{i}",
                event_type="user.created",
                processed_at=datetime.now(UTC) - timedelta(days=3),
            )
            db_session.add(webhook)
        await db_session.flush()

        repo = ProcessedWebhookRepository(db_session)
        deleted_count = await repo.delete_older_than(days=7)

        assert deleted_count == 0

    async def test_different_svix_ids_both_succeed(self, db_session):
        """Different svix_ids can both be marked as processed."""
        repo = ProcessedWebhookRepository(db_session)

        result1 = await repo.try_mark_processed("svix_aaa", "user.created")
        result2 = await repo.try_mark_processed("svix_bbb", "user.created")

        assert result1 is True
        assert result2 is True
