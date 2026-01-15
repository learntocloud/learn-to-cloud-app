"""Repository for webhook idempotency tracking."""

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
        """
        processed = ProcessedWebhook(id=svix_id, event_type=event_type)
        self.db.add(processed)
        try:
            await self.db.flush()
        except IntegrityError:
            return False
        return True
