"""Repository for persisted user scenarios.

Handles database operations for user-specific generated scenarios.
Scenarios are persisted permanently to maintain a complete learning record
and avoid regenerating the same scenario multiple times.
"""

from sqlalchemy import delete, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from models import UserScenario


class ScenarioRepository:
    """Repository for user scenario persistence."""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def get(
        self,
        user_id: str,
        question_id: str,
    ) -> str | None:
        """Get a user's scenario for a question if it exists.

        Args:
            user_id: The user's ID
            question_id: The question ID

        Returns:
            The scenario prompt if found, None otherwise
        """
        stmt = select(UserScenario.scenario_prompt).where(
            UserScenario.user_id == user_id,
            UserScenario.question_id == question_id,
        )
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()

    async def upsert(
        self,
        user_id: str,
        question_id: str,
        scenario_prompt: str,
    ) -> None:
        """Insert a scenario for a user/question pair, or no-op if exists.

        Once a scenario is generated for a user, it's permanent. This uses
        PostgreSQL's ON CONFLICT DO NOTHING to preserve the original scenario.
        """
        stmt = insert(UserScenario).values(
            user_id=user_id,
            question_id=question_id,
            scenario_prompt=scenario_prompt,
        )
        stmt = stmt.on_conflict_do_nothing(constraint="uq_user_scenario")
        await self.db.execute(stmt)
        await self.db.flush()

    async def delete(self, user_id: str, question_id: str) -> None:
        """Delete a scenario (used when user account is deleted)."""
        stmt = delete(UserScenario).where(
            UserScenario.user_id == user_id,
            UserScenario.question_id == question_id,
        )
        await self.db.execute(stmt)
        await self.db.flush()
