"""Repository for grading concepts operations."""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from models import GradingConcept


class GradingConceptRepository:
    """Repository for grading concept lookups."""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def get_by_question_id(self, question_id: str) -> list[str] | None:
        """Get expected concepts for a question.

        Args:
            question_id: The question ID (e.g., "phase0-topic4-q1")

        Returns:
            List of expected concepts, or None if not found
        """
        result = await self.db.execute(
            select(GradingConcept.expected_concepts).where(
                GradingConcept.question_id == question_id
            )
        )
        row = result.scalar_one_or_none()
        return row if row else None

    async def exists(self, question_id: str) -> bool:
        """Check if grading concepts exist for a question."""
        result = await self.db.execute(
            select(GradingConcept.question_id).where(
                GradingConcept.question_id == question_id
            )
        )
        return result.scalar_one_or_none() is not None
