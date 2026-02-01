"""Repository for daily metrics operations."""

from collections.abc import Sequence
from datetime import date

from sqlalchemy import delete, func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from models import (
    ActivityType,
    Certificate,
    DailyMetrics,
    QuestionAttempt,
    StepProgress,
    Submission,
    User,
    UserActivity,
)


class MetricsRepository:
    """Repository for aggregated metrics operations."""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def get_metrics_range(
        self,
        start_date: date,
        end_date: date,
    ) -> Sequence[DailyMetrics]:
        """Get daily metrics for a date range."""
        result = await self.db.execute(
            select(DailyMetrics)
            .where(
                DailyMetrics.metric_date >= start_date,
                DailyMetrics.metric_date <= end_date,
            )
            .order_by(DailyMetrics.metric_date.desc())
        )
        return result.scalars().all()

    async def get_latest_metrics_date(self) -> date | None:
        """Get the most recent date with metrics."""
        result = await self.db.execute(select(func.max(DailyMetrics.metric_date)))
        return result.scalar_one_or_none()

    async def upsert_metrics(self, metrics: DailyMetrics) -> DailyMetrics:
        """Insert or update metrics for a date."""
        stmt = insert(DailyMetrics).values(
            metric_date=metrics.metric_date,
            active_users=metrics.active_users,
            new_signups=metrics.new_signups,
            returning_users=metrics.returning_users,
            steps_completed=metrics.steps_completed,
            questions_attempted=metrics.questions_attempted,
            questions_passed=metrics.questions_passed,
            hands_on_submitted=metrics.hands_on_submitted,
            hands_on_validated=metrics.hands_on_validated,
            phases_completed=metrics.phases_completed,
            certificates_earned=metrics.certificates_earned,
            question_pass_rate=metrics.question_pass_rate,
        )
        stmt = stmt.on_conflict_do_update(
            index_elements=["metric_date"],
            set_={
                "active_users": stmt.excluded.active_users,
                "new_signups": stmt.excluded.new_signups,
                "returning_users": stmt.excluded.returning_users,
                "steps_completed": stmt.excluded.steps_completed,
                "questions_attempted": stmt.excluded.questions_attempted,
                "questions_passed": stmt.excluded.questions_passed,
                "hands_on_submitted": stmt.excluded.hands_on_submitted,
                "hands_on_validated": stmt.excluded.hands_on_validated,
                "phases_completed": stmt.excluded.phases_completed,
                "certificates_earned": stmt.excluded.certificates_earned,
                "question_pass_rate": stmt.excluded.question_pass_rate,
            },
        )
        await self.db.execute(stmt)
        await self.db.flush()
        return metrics

    async def delete_metrics_range(
        self,
        start_date: date,
        end_date: date,
    ) -> int:
        """Delete metrics in a date range. Returns count deleted."""
        result = await self.db.execute(
            delete(DailyMetrics).where(
                DailyMetrics.metric_date >= start_date,
                DailyMetrics.metric_date <= end_date,
            )
        )
        return result.rowcount

    # -------------------------------------------------------------------------
    # Aggregation queries (used by aggregation service)
    # -------------------------------------------------------------------------

    async def count_active_users(self, target_date: date) -> int:
        """Count distinct users with activity on a date."""
        result = await self.db.execute(
            select(func.count(func.distinct(UserActivity.user_id))).where(
                UserActivity.activity_date == target_date
            )
        )
        return result.scalar_one()

    async def count_new_signups(self, target_date: date) -> int:
        """Count users created on a date."""
        result = await self.db.execute(
            select(func.count(User.id)).where(func.date(User.created_at) == target_date)
        )
        return result.scalar_one()

    async def count_steps_completed(self, target_date: date) -> int:
        """Count steps completed on a date."""
        result = await self.db.execute(
            select(func.count(StepProgress.id)).where(
                func.date(StepProgress.completed_at) == target_date
            )
        )
        return result.scalar_one()

    async def count_questions_attempted(self, target_date: date) -> int:
        """Count question attempts on a date."""
        result = await self.db.execute(
            select(func.count(QuestionAttempt.id)).where(
                func.date(QuestionAttempt.created_at) == target_date
            )
        )
        return result.scalar_one()

    async def count_questions_passed(self, target_date: date) -> int:
        """Count passed question attempts on a date."""
        result = await self.db.execute(
            select(func.count(QuestionAttempt.id)).where(
                func.date(QuestionAttempt.created_at) == target_date,
                QuestionAttempt.is_passed == True,  # noqa: E712
            )
        )
        return result.scalar_one()

    async def count_hands_on_submitted(self, target_date: date) -> int:
        """Count hands-on submissions created on a date."""
        result = await self.db.execute(
            select(func.count(Submission.id)).where(
                func.date(Submission.created_at) == target_date
            )
        )
        return result.scalar_one()

    async def count_hands_on_validated(self, target_date: date) -> int:
        """Count hands-on submissions validated on a date."""
        result = await self.db.execute(
            select(func.count(Submission.id)).where(
                func.date(Submission.validated_at) == target_date,
                Submission.is_validated == True,  # noqa: E712
            )
        )
        return result.scalar_one()

    async def count_phases_completed(self, target_date: date) -> int:
        """Count phase completion activities on a date."""
        result = await self.db.execute(
            select(func.count(UserActivity.id)).where(
                UserActivity.activity_date == target_date,
                UserActivity.activity_type == ActivityType.PHASE_COMPLETE,
            )
        )
        return result.scalar_one()

    async def count_certificates_earned(self, target_date: date) -> int:
        """Count certificates issued on a date."""
        result = await self.db.execute(
            select(func.count(Certificate.id)).where(
                func.date(Certificate.issued_at) == target_date
            )
        )
        return result.scalar_one()

    async def get_user_ids_active_on_date(self, target_date: date) -> set[str]:
        """Get set of user IDs with activity on a date."""
        result = await self.db.execute(
            select(func.distinct(UserActivity.user_id)).where(
                UserActivity.activity_date == target_date
            )
        )
        return {row[0] for row in result.all()}

    async def get_user_ids_created_on_date(self, target_date: date) -> set[str]:
        """Get set of user IDs created on a date."""
        result = await self.db.execute(
            select(User.id).where(func.date(User.created_at) == target_date)
        )
        return {row[0] for row in result.all()}

    # -------------------------------------------------------------------------
    # Cumulative / totals (for dashboard)
    # -------------------------------------------------------------------------

    async def get_total_users(self) -> int:
        """Get total user count."""
        result = await self.db.execute(select(func.count(User.id)))
        return result.scalar_one()

    async def get_total_certificates(self) -> int:
        """Get total certificates issued."""
        result = await self.db.execute(select(func.count(Certificate.id)))
        return result.scalar_one()
