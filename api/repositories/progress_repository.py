"""Repository for step, question, and phase progress operations."""

from collections.abc import Sequence
from datetime import UTC, datetime

from sqlalchemy import delete, func, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from models import QuestionAttempt, StepProgress, UserPhaseProgress


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
        return {row[0] for row in result.all()}

    async def get_all_passed_by_user(
        self,
        user_id: str,
    ) -> dict[str, set[str]]:
        """Get all passed questions for a user, grouped by topic."""
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
        scenario_prompt: str | None = None,
        llm_feedback: str | None = None,
        confidence_score: float | None = None,
        *,
        phase_id: int | None = None,
    ) -> QuestionAttempt:
        """Create a new question attempt record."""
        if phase_id is None:
            phase_id = _parse_phase_id_from_topic_id(topic_id)
            if phase_id is None:
                raise ValueError(f"Invalid topic_id format: {topic_id}")
        attempt = QuestionAttempt(
            user_id=user_id,
            topic_id=topic_id,
            phase_id=phase_id,
            question_id=question_id,
            is_passed=is_passed,
            user_answer=user_answer or "",
            scenario_prompt=scenario_prompt,
            llm_feedback=llm_feedback,
            confidence_score=confidence_score,
        )
        self.db.add(attempt)
        await self.db.flush()
        return attempt

    async def get_passed_counts_by_phase(self, user_id: str) -> dict[int, int]:
        result = await self.db.execute(
            select(
                QuestionAttempt.phase_id,
                func.count(func.distinct(QuestionAttempt.question_id)),
            )
            .where(
                QuestionAttempt.user_id == user_id,
                QuestionAttempt.is_passed,
            )
            .group_by(QuestionAttempt.phase_id)
        )
        return {row[0]: row[1] for row in result.all()}

    async def get_all_passed_question_ids(self, user_id: str) -> list[str]:
        """Get all distinct passed question IDs for a user."""
        result = await self.db.execute(
            select(func.distinct(QuestionAttempt.question_id)).where(
                QuestionAttempt.user_id == user_id,
                QuestionAttempt.is_passed,
            )
        )
        return [row[0] for row in result.all()]

    async def has_passed_question(
        self,
        user_id: str,
        question_id: str,
    ) -> bool:
        """Check if user has already passed a specific question."""
        result = await self.db.execute(
            select(QuestionAttempt.id)
            .where(
                QuestionAttempt.user_id == user_id,
                QuestionAttempt.question_id == question_id,
                QuestionAttempt.is_passed,
            )
            .limit(1)
        )
        return result.scalar_one_or_none() is not None

    async def count_recent_failed_attempts(
        self,
        user_id: str,
        question_id: str,
        since: datetime,
    ) -> int:
        """Count failed attempts for a question since a given time.

        Used for attempt limiting - counts failures within the lockout window.
        """
        result = await self.db.execute(
            select(func.count(QuestionAttempt.id)).where(
                QuestionAttempt.user_id == user_id,
                QuestionAttempt.question_id == question_id,
                QuestionAttempt.is_passed.is_(False),
                QuestionAttempt.created_at >= since,
            )
        )
        return result.scalar_one()

    async def get_oldest_recent_failure(
        self,
        user_id: str,
        question_id: str,
        since: datetime,
    ) -> datetime | None:
        """Get the timestamp of the oldest failed attempt in the lockout window.

        Used to calculate when the lockout will expire.
        """
        result = await self.db.execute(
            select(func.min(QuestionAttempt.created_at)).where(
                QuestionAttempt.user_id == user_id,
                QuestionAttempt.question_id == question_id,
                QuestionAttempt.is_passed.is_(False),
                QuestionAttempt.created_at >= since,
            )
        )
        return result.scalar_one_or_none()

    async def get_locked_questions(
        self,
        user_id: str,
        topic_id: str,
        since: datetime,
        max_attempts: int,
    ) -> dict[str, tuple[int, datetime]]:
        """Get questions that are locked out due to too many failed attempts.

        Returns a dict of question_id -> (failed_attempt_count, oldest_failure_time)
        for questions where failed attempts >= max_attempts within the lockout window.

        The oldest_failure_time is needed to calculate when the lockout expires
        (when the oldest failure "ages out" of the rolling window).
        """
        # Count failed attempts and get oldest failure per question
        result = await self.db.execute(
            select(
                QuestionAttempt.question_id,
                func.count(QuestionAttempt.id).label("fail_count"),
                func.min(QuestionAttempt.created_at).label("oldest_failure"),
            )
            .where(
                QuestionAttempt.user_id == user_id,
                QuestionAttempt.topic_id == topic_id,
                QuestionAttempt.is_passed.is_(False),
                QuestionAttempt.created_at >= since,
            )
            .group_by(QuestionAttempt.question_id)
            .having(func.count(QuestionAttempt.id) >= max_attempts)
        )
        return {
            row.question_id: (row.fail_count, row.oldest_failure)
            for row in result.all()
        }


def _parse_phase_id_from_topic_id(topic_id: str) -> int | None:
    if not isinstance(topic_id, str) or not topic_id.startswith("phase"):
        return None
    try:
        return int(topic_id.split("-")[0].replace("phase", ""))
    except (ValueError, IndexError):
        return None


class UserPhaseProgressRepository:
    """Repository for aggregated progress per user and phase."""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def get_by_user(self, user_id: str) -> Sequence[UserPhaseProgress]:
        result = await self.db.execute(
            select(UserPhaseProgress).where(UserPhaseProgress.user_id == user_id)
        )
        return result.scalars().all()

    async def get_by_user_and_phase(
        self, user_id: str, phase_id: int
    ) -> UserPhaseProgress | None:
        result = await self.db.execute(
            select(UserPhaseProgress).where(
                UserPhaseProgress.user_id == user_id,
                UserPhaseProgress.phase_id == phase_id,
            )
        )
        return result.scalar_one_or_none()

    async def upsert_counts(
        self,
        user_id: str,
        phase_id: int,
        steps_completed: int,
        questions_passed: int,
        hands_on_validated_count: int,
    ) -> None:
        now = datetime.now(UTC)
        stmt = (
            pg_insert(UserPhaseProgress)
            .values(
                user_id=user_id,
                phase_id=phase_id,
                steps_completed=steps_completed,
                questions_passed=questions_passed,
                hands_on_validated_count=hands_on_validated_count,
                created_at=now,
                updated_at=now,
            )
            .on_conflict_do_update(
                index_elements=["user_id", "phase_id"],
                set_={
                    "steps_completed": steps_completed,
                    "questions_passed": questions_passed,
                    "hands_on_validated_count": hands_on_validated_count,
                    "updated_at": now,
                },
            )
        )
        await self.db.execute(stmt)

    async def apply_delta(
        self,
        user_id: str,
        phase_id: int,
        *,
        steps_delta: int = 0,
        questions_delta: int = 0,
        hands_on_delta: int = 0,
    ) -> None:
        now = datetime.now(UTC)
        await self._ensure_row(user_id, phase_id, now)

        stmt = (
            update(UserPhaseProgress)
            .where(
                UserPhaseProgress.user_id == user_id,
                UserPhaseProgress.phase_id == phase_id,
            )
            .values(
                steps_completed=func.greatest(
                    UserPhaseProgress.steps_completed + steps_delta, 0
                ),
                questions_passed=func.greatest(
                    UserPhaseProgress.questions_passed + questions_delta, 0
                ),
                hands_on_validated_count=func.greatest(
                    UserPhaseProgress.hands_on_validated_count + hands_on_delta, 0
                ),
                updated_at=now,
            )
        )
        await self.db.execute(stmt)

    async def _ensure_row(self, user_id: str, phase_id: int, now: datetime) -> None:
        stmt = pg_insert(UserPhaseProgress).values(
            user_id=user_id,
            phase_id=phase_id,
            steps_completed=0,
            questions_passed=0,
            hands_on_validated_count=0,
            created_at=now,
            updated_at=now,
        )
        stmt = stmt.on_conflict_do_nothing(index_elements=["user_id", "phase_id"])
        await self.db.execute(stmt)
