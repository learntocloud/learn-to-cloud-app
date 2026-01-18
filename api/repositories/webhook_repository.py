"""Repository for webhook idempotency tracking."""

from datetime import UTC, datetime, timedelta

from sqlalchemy import delete
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from models import ProcessedWebhook


class ProcessedWebhookRepository:
    """Repository for ProcessedWebhook (svix-id) tracking."""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def try_mark_processed(self, svix_id: str, event_type: str) -> bool:
        """Attempt to mark a webhook as processed.

        Returns:
            True if this call successfully marked the webhook as processed.
            False if the webhook was already processed.

        Notes:
            Uses an INSERT + flush so idempotency works under concurrency.
            Rollback on IntegrityError to restore session to a valid state.
        """
        processed = ProcessedWebhook(id=svix_id, event_type=event_type)
        self.db.add(processed)
        try:
            await self.db.flush()
        except IntegrityError:
            await self.db.rollback()
            return False
        return True

    async def delete_older_than(self, *, days: int = 7) -> int:
        """Delete processed webhook rows older than `days`.

        Notes:
            This does not commit; the caller controls the transaction.
        """
        cutoff = datetime.now(UTC) - timedelta(days=days)
        result = await self.db.execute(
            delete(ProcessedWebhook).where(ProcessedWebhook.processed_at < cutoff)
        )
        return result.rowcount or 0
