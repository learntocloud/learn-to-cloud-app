"""Submission repository for hands-on validation database operations."""

from datetime import UTC, datetime, timedelta
from typing import NamedTuple

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from models import Submission, SubmissionType


class ValidatedSubmissionSummary(NamedTuple):
    """Lightweight projection for validated submission display."""

    requirement_id: str
    submission_type: SubmissionType
    phase_id: int
    submitted_value: str
    validated_at: datetime | None


class SubmissionRepository:
    """Repository for Submission database operations."""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_by_user_and_phase(
        self, user_id: int, phase_id: int
    ) -> list[Submission]:
        """Get the latest submission per requirement for a user in a phase."""
        # Subquery to find the max created_at per requirement
        latest_sq = (
            select(
                Submission.requirement_id,
                func.max(Submission.created_at).label("max_created"),
            )
            .where(
                Submission.user_id == user_id,
                Submission.phase_id == phase_id,
            )
            .group_by(Submission.requirement_id)
            .subquery()
        )
        result = await self.db.execute(
            select(Submission)
            .join(
                latest_sq,
                (Submission.requirement_id == latest_sq.c.requirement_id)
                & (Submission.created_at == latest_sq.c.max_created),
            )
            .where(
                Submission.user_id == user_id,
                Submission.phase_id == phase_id,
            )
        )
        return list(result.scalars().all())

    async def get_validated_by_user(
        self, user_id: int
    ) -> list[ValidatedSubmissionSummary]:
        """Get validated submission summaries for a user (one per requirement)."""
        # Subquery: earliest validated_at per requirement
        earliest_sq = (
            select(
                Submission.requirement_id,
                func.min(Submission.validated_at).label("min_validated"),
            )
            .where(
                Submission.user_id == user_id,
                Submission.is_validated.is_(True),
            )
            .group_by(Submission.requirement_id)
            .subquery()
        )
        result = await self.db.execute(
            select(
                Submission.requirement_id,
                Submission.submission_type,
                Submission.phase_id,
                Submission.submitted_value,
                Submission.validated_at,
            )
            .join(
                earliest_sq,
                (Submission.requirement_id == earliest_sq.c.requirement_id)
                & (Submission.validated_at == earliest_sq.c.min_validated),
            )
            .where(
                Submission.user_id == user_id,
                Submission.is_validated.is_(True),
            )
            .order_by(Submission.phase_id, Submission.validated_at)
        )
        return [ValidatedSubmissionSummary(*row) for row in result.all()]

    async def get_by_user_and_requirement(
        self, user_id: int, requirement_id: str
    ) -> Submission | None:
        """Get the latest submission for a user and requirement."""
        result = await self.db.execute(
            select(Submission)
            .where(
                Submission.user_id == user_id,
                Submission.requirement_id == requirement_id,
            )
            .order_by(Submission.created_at.desc())
            .limit(1)
        )
        return result.scalar_one_or_none()

    async def create(
        self,
        user_id: int,
        requirement_id: str,
        submission_type: SubmissionType,
        phase_id: int,
        submitted_value: str,
        extracted_username: str | None,
        is_validated: bool,
        verification_completed: bool = True,
        feedback_json: str | None = None,
        validation_message: str | None = None,
        cloud_provider: str | None = None,
    ) -> Submission:
        """Create a new submission attempt.

        Automatically determines the next attempt number for the
        user+requirement pair.

        Args:
            verification_completed: Whether the verification logic actually ran.
                Set to False when blocked by server errors (e.g., LLM CLI down).
                Only completed verifications count toward cooldowns.
            feedback_json: JSON-serialized task feedback for CODE_ANALYSIS submissions.
            cloud_provider: Cloud provider slug ("aws", "azure", "gcp") for
                multi-cloud labs. None for non-multi-cloud submissions.
        """
        now = datetime.now(UTC)

        # Get the next attempt number
        result = await self.db.execute(
            select(func.coalesce(func.max(Submission.attempt_number), 0)).where(
                Submission.user_id == user_id,
                Submission.requirement_id == requirement_id,
            )
        )
        max_attempt = result.scalar_one()

        submission = Submission(
            user_id=user_id,
            requirement_id=requirement_id,
            attempt_number=max_attempt + 1,
            submission_type=submission_type,
            phase_id=phase_id,
            submitted_value=submitted_value,
            extracted_username=extracted_username,
            is_validated=is_validated,
            validated_at=now if is_validated else None,
            verification_completed=verification_completed,
            feedback_json=feedback_json,
            validation_message=validation_message,
            cloud_provider=cloud_provider,
        )
        self.db.add(submission)
        await self.db.flush()
        return submission

    async def get_last_submission_time(
        self,
        user_id: int,
        requirement_id: str,
    ) -> datetime | None:
        """Get the timestamp of the user's most recent completed verification.

        Used to enforce cooldown periods between verification attempts.
        Only considers submissions where verification actually ran (not blocked
        by server errors), so users aren't penalized for infrastructure issues.

        Returns:
            The updated_at timestamp of the last completed verification,
            or None if no completed verification exists.
        """
        result = await self.db.execute(
            select(Submission.updated_at)
            .where(
                Submission.user_id == user_id,
                Submission.requirement_id == requirement_id,
                Submission.verification_completed.is_(True),
            )
            .order_by(Submission.updated_at.desc())
            .limit(1)
        )
        row = result.scalar_one_or_none()
        return row

    async def count_submissions_today(self, user_id: int) -> int:
        """Count completed verification attempts by this user in the last 24 hours.

        Used to enforce a global daily submission cap across all requirements.
        Only counts submissions where verification actually ran.
        """
        cutoff = datetime.now(UTC) - timedelta(hours=24)
        result = await self.db.execute(
            select(func.count())
            .select_from(Submission)
            .where(
                Submission.user_id == user_id,
                Submission.verification_completed.is_(True),
                Submission.updated_at >= cutoff,
            )
        )
        return result.scalar_one() or 0
