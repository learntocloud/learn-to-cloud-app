"""Repository for step progress operations."""

from sqlalchemy import delete, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from models import StepProgress


class StepProgressRepository:
    """Repository for step progress (learning steps completion)."""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def get_completed_step_ids(
        self,
        user_id: int,
        topic_id: str,
    ) -> set[str]:
        """Get set of completed step IDs for a user in a topic."""
        result = await self.db.execute(
            select(StepProgress.step_id).where(
                StepProgress.user_id == user_id,
                StepProgress.topic_id == topic_id,
            )
        )
        return {row[0] for row in result.all()}

    async def create_if_not_exists(
        self,
        user_id: int,
        topic_id: str,
        step_id: str,
        step_order: int,
        phase_id: int,
    ) -> StepProgress | None:
        """Atomically create a step progress record if it doesn't exist.

        Uses INSERT ... ON CONFLICT DO NOTHING RETURNING to check and insert
        in a single round-trip instead of SELECT + INSERT (2 round-trips).

        Returns:
            The created StepProgress if inserted, or None if already existed.
        """
        stmt = (
            pg_insert(StepProgress)
            .values(
                user_id=user_id,
                topic_id=topic_id,
                step_id=step_id,
                phase_id=phase_id,
                step_order=step_order,
            )
            .on_conflict_do_nothing(
                constraint="uq_user_topic_step",
            )
            .returning(StepProgress)
        )
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()

    async def delete_step(
        self,
        user_id: int,
        topic_id: str,
        step_id: str,
    ) -> int:
        """Delete a single step progress record."""
        result = await self.db.execute(
            delete(StepProgress).where(
                StepProgress.user_id == user_id,
                StepProgress.topic_id == topic_id,
                StepProgress.step_id == step_id,
            )
        )
        return getattr(result, "rowcount", 0) or 0

    async def get_completed_for_topics(
        self,
        user_id: int,
        topic_ids: list[str],
    ) -> dict[str, set[str]]:
        """Get completed steps for a user, filtered to specific topics.

        More targeted than get_all_completed_by_user when only one phase
        is needed (avoids fetching unrelated phases).
        """
        if not topic_ids:
            return {}

        result = await self.db.execute(
            select(StepProgress.topic_id, StepProgress.step_id).where(
                StepProgress.user_id == user_id,
                StepProgress.topic_id.in_(topic_ids),
            )
        )

        by_topic: dict[str, set[str]] = {}
        for row in result.all():
            by_topic.setdefault(row.topic_id, set()).add(row.step_id)
        return by_topic
