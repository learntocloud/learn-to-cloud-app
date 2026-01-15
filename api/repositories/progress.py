"""Repository for step and question progress operations."""

from collections.abc import Sequence

from sqlalchemy import distinct, func, select
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

    async def get_all_by_user(
        self,
        user_id: str,
    ) -> dict[str, list[int]]:
        """Get all completed steps for a user, grouped by topic.

        Returns a dict mapping topic_id to list of completed step orders.
        """
        result = await self.db.execute(
            select(StepProgress.topic_id, StepProgress.step_order)
            .where(StepProgress.user_id == user_id)
            .order_by(StepProgress.topic_id, StepProgress.step_order)
        )

        topic_steps: dict[str, list[int]] = {}
        for row in result.all():
            topic_id = row.topic_id
            if topic_id not in topic_steps:
                topic_steps[topic_id] = []
            topic_steps[topic_id].append(row.step_order)

        return topic_steps

    async def get_all_topic_ids(self, user_id: str) -> list[str]:
        """Get all topic IDs where user has completed at least one step."""
        result = await self.db.execute(
            select(distinct(StepProgress.topic_id)).where(
                StepProgress.user_id == user_id
            )
        )
        return [row[0] for row in result.all()]

    async def count_by_phase(self, user_id: str) -> dict[int, int]:
        """Count completed steps per phase for a user.

        Parses topic_id format: phase{N}-topic{M}
        Returns dict mapping phase number to count.
        """
        result = await self.db.execute(
            select(StepProgress.topic_id).where(StepProgress.user_id == user_id)
        )

        phase_counts: dict[int, int] = {}
        for (topic_id,) in result.all():
            if not isinstance(topic_id, str) or not topic_id.startswith("phase"):
                continue
            try:
                phase_num = int(topic_id.split("-")[0].replace("phase", ""))
            except (ValueError, IndexError):
                continue
            phase_counts[phase_num] = phase_counts.get(phase_num, 0) + 1

        return phase_counts


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

    async def get_topic_stats(
        self,
        user_id: str,
        topic_id: str,
    ) -> list[dict]:
        """Get question statistics for a topic.

        Returns list of dicts with question_id, attempts_count, last_attempt_at.
        """
        result = await self.db.execute(
            select(
                QuestionAttempt.question_id,
                func.count(QuestionAttempt.id).label("attempts_count"),
                func.max(QuestionAttempt.created_at).label("last_attempt_at"),
            )
            .where(
                QuestionAttempt.user_id == user_id,
                QuestionAttempt.topic_id == topic_id,
            )
            .group_by(QuestionAttempt.question_id)
        )

        return [
            {
                "question_id": row.question_id,
                "attempts_count": int(row.attempts_count),
                "last_attempt_at": row.last_attempt_at,
            }
            for row in result.all()
        ]

    async def create(
        self,
        user_id: str,
        topic_id: str,
        question_id: str,
        is_passed: bool,
        user_answer: str | None = None,
    ) -> QuestionAttempt:
        """Create a new question attempt record."""
        attempt = QuestionAttempt(
            user_id=user_id,
            topic_id=topic_id,
            question_id=question_id,
            is_passed=is_passed,
            user_answer=user_answer or "",
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

    async def count_passed_by_phase(self, user_id: str) -> dict[int, int]:
        """Count passed questions per phase for a user.

        Parses question_id format: phase{N}-topic{M}-q{X}
        Returns dict mapping phase number to count.
        """
        question_ids = await self.get_all_passed_question_ids(user_id)
        phase_counts: dict[int, int] = {}
        for question_id in question_ids:
            if question_id.startswith("phase"):
                try:
                    phase_num = int(question_id.split("-")[0].replace("phase", ""))
                    phase_counts[phase_num] = phase_counts.get(phase_num, 0) + 1
                except (ValueError, IndexError):
                    continue
        return phase_counts
