"""Repository for denormalized user phase progress."""

from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from models import UserPhaseProgress


class UserPhaseProgressRepository:
    """Repository for UserPhaseProgress denormalized table."""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_by_user(self, user_id: int) -> dict[int, UserPhaseProgress]:
        """Get all phase progress records for a user.

        Returns dict mapping phase_id → UserPhaseProgress.
        """
        result = await self.db.execute(
            select(UserPhaseProgress).where(UserPhaseProgress.user_id == user_id)
        )
        return {row.phase_id: row for row in result.scalars().all()}

    async def increment_steps(
        self, user_id: int, phase_id: int, delta: int = 1
    ) -> None:
        """Increment completed_steps count. Creates row if not exists."""
        now = datetime.now(UTC)
        stmt = pg_insert(UserPhaseProgress).values(
            user_id=user_id,
            phase_id=phase_id,
            completed_steps=max(delta, 0),
            validated_submissions=0,
            updated_at=now,
        )
        stmt = stmt.on_conflict_do_update(
            constraint="uq_user_phase_progress",
            set_={
                "completed_steps": UserPhaseProgress.completed_steps + delta,
                "updated_at": now,
            },
        )
        await self.db.execute(stmt)

    async def increment_submissions(
        self, user_id: int, phase_id: int, delta: int = 1
    ) -> None:
        """Increment validated_submissions count. Creates row if not exists."""
        now = datetime.now(UTC)
        stmt = pg_insert(UserPhaseProgress).values(
            user_id=user_id,
            phase_id=phase_id,
            completed_steps=0,
            validated_submissions=max(delta, 0),
            updated_at=now,
        )
        stmt = stmt.on_conflict_do_update(
            constraint="uq_user_phase_progress",
            set_={
                "validated_submissions": UserPhaseProgress.validated_submissions
                + delta,
                "updated_at": now,
            },
        )
        await self.db.execute(stmt)

    async def recalculate_steps_for_phase(
        self, user_id: int, phase_id: int, new_count: int
    ) -> None:
        """Set completed_steps to an exact count.

        Used after cascading uncomplete.
        """
        now = datetime.now(UTC)
        stmt = pg_insert(UserPhaseProgress).values(
            user_id=user_id,
            phase_id=phase_id,
            completed_steps=new_count,
            validated_submissions=0,
            updated_at=now,
        )
        stmt = stmt.on_conflict_do_update(
            constraint="uq_user_phase_progress",
            set_={
                "completed_steps": new_count,
                "updated_at": now,
            },
        )
        await self.db.execute(stmt)
