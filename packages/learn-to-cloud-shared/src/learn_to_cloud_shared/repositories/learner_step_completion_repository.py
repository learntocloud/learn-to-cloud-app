"""Repository for authoritative learner step completions."""

from __future__ import annotations

from collections.abc import Iterable
from datetime import datetime
from uuid import UUID

from sqlalchemy import delete, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from learn_to_cloud_shared.models import LearnerStepCompletion


class LearnerStepCompletionRepository:
    """Repository for learner step completion (curriculum-decoupled) records."""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def get_completed_step_uuids(
        self,
        user_id: int,
        step_uuids: Iterable[UUID],
    ) -> set[UUID]:
        """Return which of the given step UUIDs the user has completed."""
        uuids = list(step_uuids)
        if not uuids:
            return set()

        result = await self.db.execute(
            select(LearnerStepCompletion.step_uuid).where(
                LearnerStepCompletion.user_id == user_id,
                LearnerStepCompletion.step_uuid.in_(uuids),
            )
        )
        return {row[0] for row in result.all()}

    async def create_if_not_exists(
        self,
        *,
        user_id: int,
        step_uuid: UUID,
        completed_at: datetime | None = None,
    ) -> None:
        """Atomically create a completion record unless it already exists."""
        values: dict[str, object] = {"user_id": user_id, "step_uuid": step_uuid}
        if completed_at is not None:
            values["completed_at"] = completed_at
        stmt = (
            pg_insert(LearnerStepCompletion)
            .values(**values)
            .on_conflict_do_nothing(
                index_elements=["user_id", "step_uuid"],
            )
        )
        await self.db.execute(stmt)

    async def delete(self, *, user_id: int, step_uuid: UUID) -> None:
        """Delete a single completion record, if present."""
        await self.db.execute(
            delete(LearnerStepCompletion).where(
                LearnerStepCompletion.user_id == user_id,
                LearnerStepCompletion.step_uuid == step_uuid,
            )
        )
