"""Repository for step and question progress operations."""

from collections.abc import Sequence

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from models import QuestionAttempt, StepProgress


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
        return set(row[0] for row in result.all())

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
    ) -> StepProgress:
        """Create a new step progress record."""
        step_progress = StepProgress(
            user_id=user_id,
            topic_id=topic_id,
            step_order=step_order,
        )
        self.db.add(step_progress)
        await self.db.flush()
        return step_progress

    async def delete_from_step(
        self,
        user_id: str,
        topic_id: str,
        from_step_order: int,
    ) -> int:
        """Delete step progress from a given step order onwards (cascading uncomplete).

        Returns the number of deleted rows.
        """
        from sqlalchemy import delete

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
        """Get all completed steps for a user, grouped by topic.

        Returns a dict mapping topic_id to set of completed step_orders.
        """
        result = await self.db.execute(
            select(StepProgress.topic_id, StepProgress.step_order).where(
                StepProgress.user_id == user_id
            )
        )

        by_topic: dict[str, set[int]] = {}
        for row in result.all():
            by_topic.setdefault(row.topic_id, set()).add(row.step_order)
        return by_topic


class QuestionAttemptRepository:
    """Repository for question attempts (quiz/knowledge check progress)."""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def get_by_user_and_topic(
        self,
        user_id: str,
        topic_id: str,
    ) -> Sequence[QuestionAttempt]:
        """Get all question attempts for a user in a topic."""
        result = await self.db.execute(
            select(QuestionAttempt)
            .where(
                QuestionAttempt.user_id == user_id,
                QuestionAttempt.topic_id == topic_id,
            )
            .order_by(QuestionAttempt.created_at.desc())
        )
        return result.scalars().all()

    async def get_passed_question_ids(
        self,
        user_id: str,
        topic_id: str,
    ) -> set[str]:
        """Get IDs of questions the user has passed in a topic."""
        result = await self.db.execute(
            select(QuestionAttempt.question_id)
            .where(
                QuestionAttempt.user_id == user_id,
                QuestionAttempt.topic_id == topic_id,
                QuestionAttempt.is_passed,
            )
            .distinct()
        )
        return set(row[0] for row in result.all())

    async def get_all_passed_by_user(
        self,
        user_id: str,
    ) -> dict[str, set[str]]:
        """Get all passed questions for a user, grouped by topic.

        Returns a dict mapping topic_id to set of passed question_ids.
        """
        result = await self.db.execute(
            select(QuestionAttempt.topic_id, QuestionAttempt.question_id)
            .where(
                QuestionAttempt.user_id == user_id,
                QuestionAttempt.is_passed,
            )
            .distinct()
        )

        topic_passed: dict[str, set[str]] = {}
        for row in result.all():
            topic_id = row.topic_id
            if topic_id not in topic_passed:
                topic_passed[topic_id] = set()
            topic_passed[topic_id].add(row.question_id)

        return topic_passed

    async def create(
        self,
        user_id: str,
        topic_id: str,
        question_id: str,
        is_passed: bool,
        user_answer: str | None = None,
        llm_feedback: str | None = None,
        confidence_score: float | None = None,
    ) -> QuestionAttempt:
        """Create a new question attempt record."""
        attempt = QuestionAttempt(
            user_id=user_id,
            topic_id=topic_id,
            question_id=question_id,
            is_passed=is_passed,
            user_answer=user_answer or "",
            llm_feedback=llm_feedback,
            confidence_score=confidence_score,
        )
        self.db.add(attempt)
        await self.db.flush()
        return attempt

    async def get_all_passed_question_ids(self, user_id: str) -> list[str]:
        """Get all distinct passed question IDs for a user."""
        result = await self.db.execute(
            select(func.distinct(QuestionAttempt.question_id)).where(
                QuestionAttempt.user_id == user_id,
                QuestionAttempt.is_passed.is_(True),
            )
        )
        return [row[0] for row in result.all()]
