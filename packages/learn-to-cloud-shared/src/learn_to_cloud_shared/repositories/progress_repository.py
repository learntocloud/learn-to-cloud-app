"""Repository for step progress operations.

After Phase D.1c (#465), ``step_progress`` references the curriculum
solely via ``step_uuid`` (FK to ``steps.uuid``). All public methods
accept and return curriculum step UUIDs; callers convert to or from
the human-readable step IDs when needed.
"""

from collections.abc import Iterable
from uuid import UUID

from sqlalchemy import delete, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from learn_to_cloud_shared.models import StepProgress


class StepProgressRepository:
    """Repository for step progress (learning steps completion)."""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def get_completed_step_uuids(
        self,
        user_id: int,
        step_uuids: Iterable[UUID],
    ) -> set[UUID]:
        """Return which of the given step UUIDs the user has completed.

        Caller passes the candidate UUIDs (typically a topic's
        ``learning_steps[].uuid``); only intersecting completions come
        back. Returning an empty set for an empty input avoids a
        round-trip with an empty IN-list.
        """
        uuids = list(step_uuids)
        if not uuids:
            return set()

        result = await self.db.execute(
            select(StepProgress.step_uuid).where(
                StepProgress.user_id == user_id,
                StepProgress.step_uuid.in_(uuids),
            )
        )
        return {row[0] for row in result.all()}

    async def create_if_not_exists(
        self,
        user_id: int,
        step_uuid: UUID,
    ) -> StepProgress | None:
        """Atomically create a step progress record if it doesn't exist.

        Uses INSERT ... ON CONFLICT DO NOTHING RETURNING to check and
        insert in a single round-trip instead of SELECT + INSERT.

        Returns:
            The created StepProgress if inserted, or None if already existed.
        """
        stmt = (
            pg_insert(StepProgress)
            .values(user_id=user_id, step_uuid=step_uuid)
            .on_conflict_do_nothing(
                constraint="uq_step_progress_user_step",
            )
            .returning(StepProgress)
        )
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()

    async def delete_step(
        self,
        user_id: int,
        step_uuid: UUID,
    ) -> int:
        """Delete a single step progress record."""
        result = await self.db.execute(
            delete(StepProgress).where(
                StepProgress.user_id == user_id,
                StepProgress.step_uuid == step_uuid,
            )
        )
        return getattr(result, "rowcount", 0) or 0
