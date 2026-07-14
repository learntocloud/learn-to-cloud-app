"""Repository for the authoritative ``learner_step_completions`` table.

Coexists with :class:`~learn_to_cloud_shared.repositories.progress_repository.
StepProgressRepository` during the PR5/PR6 migration window: callers
explicitly dual-write here alongside ``step_progress``, while a temporary
database trigger (migration 0049) also mirrors any remaining legacy-only
``step_progress`` writer into this table. Both the explicit writes and the
trigger use ``ON CONFLICT DO NOTHING`` / a plain ``DELETE``, so whichever one
runs first in a transaction makes the other a no-op -- order between them
does not matter for correctness.

PR6 cuts progress reads over to this table as the authoritative source;
callers add a narrow ``step_progress`` fallback for steps not yet mirrored
here (see ``progress_service``).
"""

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
        """Return which of the given step UUIDs the user has completed.

        Mirrors ``StepProgressRepository.get_completed_step_uuids`` against
        the authoritative table. Returning an empty set for an empty input
        avoids a round-trip with an empty IN-list.
        """
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
    ) -> LearnerStepCompletion | None:
        """Atomically create a completion record if it doesn't exist.

        Returns the created row, or ``None`` if one already existed (either
        from a prior call here or from the ``step_progress`` mirror
        trigger).
        """
        values: dict[str, object] = {"user_id": user_id, "step_uuid": step_uuid}
        if completed_at is not None:
            values["completed_at"] = completed_at
        stmt = (
            pg_insert(LearnerStepCompletion)
            .values(**values)
            .on_conflict_do_nothing(
                index_elements=["user_id", "step_uuid"],
            )
            .returning(LearnerStepCompletion)
        )
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()

    async def delete(self, *, user_id: int, step_uuid: UUID) -> int:
        """Delete a single completion record, if present."""
        result = await self.db.execute(
            delete(LearnerStepCompletion).where(
                LearnerStepCompletion.user_id == user_id,
                LearnerStepCompletion.step_uuid == step_uuid,
            )
        )
        return getattr(result, "rowcount", 0) or 0
