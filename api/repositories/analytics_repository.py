"""Repository for aggregate analytics queries.

All queries return anonymous, aggregate data only — no individual user
information is exposed. Results are designed for public community
dashboards and storytelling.
"""

from datetime import UTC, datetime, timedelta

from sqlalchemy import Integer, func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from models import AnalyticsSnapshot, Certificate, StepProgress, Submission, User


class AnalyticsRepository:
    """Repository for read-only aggregate analytics queries."""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def get_total_users(self) -> int:
        """Count total registered users."""
        result = await self.db.execute(select(func.count()).select_from(User))
        return result.scalar_one() or 0

    async def get_total_certificates(self) -> int:
        """Count total certificates issued (program completions)."""
        result = await self.db.execute(select(func.count()).select_from(Certificate))
        return result.scalar_one() or 0

    async def get_active_learners(self, days: int = 30) -> int:
        """Count users with at least one step completion in the last N days."""
        cutoff = datetime.now(UTC) - timedelta(days=days)
        result = await self.db.execute(
            select(func.count(StepProgress.user_id.distinct())).where(
                StepProgress.completed_at >= cutoff,
            )
        )
        return result.scalar_one() or 0

    async def get_step_completion_histogram(
        self,
    ) -> list[tuple[int, int, int]]:
        """Get step completion histogram per phase.

        Returns:
            List of (phase_id, step_count, num_users) tuples.
            Each row says "num_users users completed exactly step_count
            steps in phase_id". Used to compute users who completed all
            steps by comparing against content-derived thresholds.
        """
        subq = (
            select(
                StepProgress.phase_id,
                StepProgress.user_id,
                func.count().label("step_count"),
            )
            .group_by(StepProgress.phase_id, StepProgress.user_id)
            .subquery()
        )
        result = await self.db.execute(
            select(
                subq.c.phase_id,
                subq.c.step_count,
                func.count().label("num_users"),
            ).group_by(subq.c.phase_id, subq.c.step_count)
        )
        return [(row[0], row[1], row[2]) for row in result.all()]

    async def get_signups_by_month(self) -> list[tuple[str, int]]:
        """Count user signups aggregated by month.

        Returns:
            List of (month_str, count) ordered chronologically.
            month_str is formatted as "YYYY-MM".
        """
        result = await self.db.execute(
            select(
                func.to_char(
                    func.date_trunc("month", User.created_at), "YYYY-MM"
                ).label("month"),
                func.count().label("cnt"),
            )
            .group_by("month")
            .order_by("month")
        )
        return [(row[0], row[1]) for row in result.all()]

    async def get_certificates_by_month(self) -> list[tuple[str, int]]:
        """Count certificates issued aggregated by month.

        Returns:
            List of (month_str, count) ordered chronologically.
        """
        result = await self.db.execute(
            select(
                func.to_char(
                    func.date_trunc("month", Certificate.issued_at), "YYYY-MM"
                ).label("month"),
                func.count().label("cnt"),
            )
            .group_by("month")
            .order_by("month")
        )
        return [(row[0], row[1]) for row in result.all()]

    async def get_submission_stats_by_phase(self) -> dict[int, tuple[int, int]]:
        """Get total and successful verification attempts per phase.

        Only counts submissions where verification actually ran
        (verification_completed=True), excluding server-error blocked attempts.

        Returns:
            Dict mapping phase_id -> (total_attempts, successful_count).
        """
        result = await self.db.execute(
            select(
                Submission.phase_id,
                func.count().label("total"),
                func.count()
                .filter(Submission.is_validated.is_(True))
                .label("successful"),
            )
            .where(Submission.verification_completed.is_(True))
            .group_by(Submission.phase_id)
        )
        return {row[0]: (row[1], row[2]) for row in result.all()}

    async def get_activity_by_day_of_week(self) -> dict[int, int]:
        """Count step completions by ISO day of week (1=Monday … 7=Sunday).

        Returns:
            Dict mapping iso_day_number -> completion_count.
        """
        result = await self.db.execute(
            select(
                func.extract("isodow", StepProgress.completed_at)
                .cast(Integer)
                .label("dow"),
                func.count().label("cnt"),
            ).group_by("dow")
        )
        return {row[0]: row[1] for row in result.all()}

    async def get_snapshot_data(self) -> str | None:
        """Read the pre-computed analytics snapshot JSON.

        Returns the raw JSON string, or None if no snapshot exists.
        """
        result = await self.db.execute(
            select(AnalyticsSnapshot.data).where(AnalyticsSnapshot.id == 1)
        )
        return result.scalar_one_or_none()

    async def upsert_snapshot(self, data_json: str, computed_at: datetime) -> None:
        """Create or update the analytics snapshot row."""
        stmt = (
            pg_insert(AnalyticsSnapshot)
            .values(id=1, data=data_json, computed_at=computed_at)
            .on_conflict_do_update(
                index_elements=["id"],
                set_={"data": data_json, "computed_at": computed_at},
            )
        )
        await self.db.execute(stmt)

    async def get_provider_distribution(self) -> list[tuple[str, int]]:
        """Count validated submissions per cloud provider.

        Only includes submissions where cloud_provider is set and the
        submission was validated.  Returns (provider, count) tuples
        ordered by count descending.
        """
        result = await self.db.execute(
            select(
                Submission.cloud_provider,
                func.count().label("cnt"),
            )
            .where(
                Submission.cloud_provider.is_not(None),
                Submission.is_validated.is_(True),
            )
            .group_by(Submission.cloud_provider)
            .order_by(func.count().desc())
        )
        return [(row[0], row[1]) for row in result.all()]
