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
            True if first time processed, False if already seen.

        Note:
            Uses savepoint so IntegrityError doesn't invalidate the session.
        """
        processed = ProcessedWebhook(id=svix_id, event_type=event_type)
        try:
            async with self.db.begin_nested():
                self.db.add(processed)
                await self.db.flush()
        except IntegrityError:
            # Savepoint rolled back automatically, session is still valid
            return False
        return True

    async def delete_older_than(self, *, days: int = 7) -> int:
        """Delete processed webhook rows older than `days`. Does not commit."""
        cutoff = datetime.now(UTC) - timedelta(days=days)
        result = await self.db.execute(
            delete(ProcessedWebhook).where(ProcessedWebhook.processed_at < cutoff)
        )
        return result.rowcount or 0
