"""Repository for step progress operations."""

from collections.abc import Sequence

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from models import StepProgress


class StepProgressRepository:
    """Repository for step progress (learning steps completion)."""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def get_by_user_and_topic(
        self,
        user_id: str,
        topic_id: str,
    ) -> Sequence[StepProgress]:
        """Get all completed steps for a user in a topic."""
        result = await self.db.execute(
            select(StepProgress)
            .where(
                StepProgress.user_id == user_id,
                StepProgress.topic_id == topic_id,
            )
            .order_by(StepProgress.step_order)
        )
        return result.scalars().all()

    async def get_completed_step_orders(
        self,
        user_id: str,
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

    async def exists(
        self,
        user_id: str,
        topic_id: str,
        step_order: int,
    ) -> bool:
        """Check if a specific step is completed."""
        result = await self.db.execute(
            select(StepProgress.id).where(
                StepProgress.user_id == user_id,
                StepProgress.topic_id == topic_id,
                StepProgress.step_order == step_order,
            )
        )
        return result.scalar_one_or_none() is not None

    async def create(
        self,
        user_id: str,
        topic_id: str,
        step_order: int,
        *,
        phase_id: int | None = None,
    ) -> StepProgress:
        """Create a new step progress record."""
        if phase_id is None:
            phase_id = _parse_phase_id_from_topic_id(topic_id)
            if phase_id is None:
                raise ValueError(f"Invalid topic_id format: {topic_id}")
        step_progress = StepProgress(
            user_id=user_id,
            topic_id=topic_id,
            phase_id=phase_id,
            step_order=step_order,
        )
        self.db.add(step_progress)
        await self.db.flush()
        return step_progress

    async def get_step_counts_by_phase(self, user_id: str) -> dict[int, int]:
        result = await self.db.execute(
            select(StepProgress.phase_id, func.count(StepProgress.id))
            .where(StepProgress.user_id == user_id)
            .group_by(StepProgress.phase_id)
        )
        return {row[0]: row[1] for row in result.all()}

    async def delete_from_step(
        self,
        user_id: str,
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

    async def get_completed_step_topic_ids(self, user_id: str) -> list[str]:
        """Get all topic IDs where user has completed steps.

        Returns topic_ids in format: phase{N}-topic{M}
        """
        result = await self.db.execute(
            select(StepProgress.topic_id)
            .where(StepProgress.user_id == user_id)
            .distinct()
        )
        return [row[0] for row in result.all()]

    async def get_all_completed_by_user(self, user_id: str) -> dict[str, set[int]]:
        """Get all completed steps for a user, grouped by topic."""
        result = await self.db.execute(
            select(StepProgress.topic_id, StepProgress.step_order).where(
                StepProgress.user_id == user_id
            )
        )

        by_topic: dict[str, set[int]] = {}
        for row in result.all():
            by_topic.setdefault(row.topic_id, set()).add(row.step_order)
        return by_topic


def _parse_phase_id_from_topic_id(topic_id: str) -> int | None:
    if not isinstance(topic_id, str) or not topic_id.startswith("phase"):
        return None
    try:
        return int(topic_id.split("-")[0].replace("phase", ""))
    except (ValueError, IndexError):
        return None
