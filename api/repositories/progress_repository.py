"""Repository for step progress operations."""

from sqlalchemy import delete, func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from models import StepProgress


class StepProgressRepository:
    """Repository for step progress (learning steps completion)."""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def get_completed_step_orders(
        self,
        user_id: int,
        topic_id: str,
    ) -> set[int]:
        """Get set of completed step orders for a user in a topic."""
        result = await self.db.execute(
            select(StepProgress.step_order).where(
                StepProgress.user_id == user_id,
                StepProgress.topic_id == topic_id,
            )
        )
        return {row[0] for row in result.all()}

    async def create_if_not_exists(
        self,
        user_id: int,
        topic_id: str,
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

    async def get_step_counts_by_phase(self, user_id: int) -> dict[int, int]:
        result = await self.db.execute(
            select(StepProgress.phase_id, func.count(StepProgress.id))
            .where(StepProgress.user_id == user_id)
            .group_by(StepProgress.phase_id)
        )
        return {row[0]: row[1] for row in result.all()}

    async def delete_from_step(
        self,
        user_id: int,
        topic_id: str,
        from_step_order: int,
    ) -> int:
        """Delete step progress from a given step onwards (cascading uncomplete)."""
        result = await self.db.execute(
            delete(StepProgress).where(
                StepProgress.user_id == user_id,
                StepProgress.topic_id == topic_id,
                StepProgress.step_order >= from_step_order,
            )
        )
        return result.rowcount or 0

    async def get_completed_for_topics(
        self,
        user_id: int,
        topic_ids: list[str],
    ) -> dict[str, set[int]]:
        """Get completed steps for a user, filtered to specific topics.

        More targeted than get_all_completed_by_user when only one phase
        is needed (avoids fetching unrelated phases).
        """
        if not topic_ids:
            return {}

        result = await self.db.execute(
            select(StepProgress.topic_id, StepProgress.step_order).where(
                StepProgress.user_id == user_id,
                StepProgress.topic_id.in_(topic_ids),
            )
        )

        by_topic: dict[str, set[int]] = {}
        for row in result.all():
            by_topic.setdefault(row.topic_id, set()).add(row.step_order)
        return by_topic
