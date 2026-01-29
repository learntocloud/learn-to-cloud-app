"""Submission repository for hands-on validation database operations."""

from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from models import Submission, SubmissionType
from repositories.utils import upsert_on_conflict


class SubmissionRepository:
    """Repository for Submission database operations."""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_by_user_and_phase(
        self, user_id: str, phase_id: int
    ) -> list[Submission]:
        """Get all submissions for a user in a specific phase."""
        result = await self.db.execute(
            select(Submission).where(
                Submission.user_id == user_id,
                Submission.phase_id == phase_id,
            )
        )
        return list(result.scalars().all())

    async def get_validated_by_user(self, user_id: str) -> list[Submission]:
        """Get all validated submissions for a user."""
        result = await self.db.execute(
            select(Submission)
            .where(
                Submission.user_id == user_id,
                Submission.is_validated.is_(True),
            )
            .order_by(Submission.phase_id, Submission.validated_at)
        )
        return list(result.scalars().all())

    async def upsert(
        self,
        user_id: str,
        requirement_id: str,
        submission_type: SubmissionType,
        phase_id: int,
        submitted_value: str,
        extracted_username: str | None,
        is_validated: bool,
        verification_completed: bool = True,
    ) -> Submission:
        """Create or update a submission.

        Uses upsert to handle concurrent submissions safely.
        Returns the created/updated submission.

        Args:
            verification_completed: Whether the verification logic actually ran.
                Set to False when blocked by server errors (e.g., Copilot CLI down).
                Only completed verifications count toward cooldowns.

        Raises:
            ValueError: If update_fields contains keys not in values.
            IntegrityError: If foreign key constraint violated (user_id not found).
            RuntimeError: If upsert unexpectedly returns no row.
        """
        now = datetime.now(UTC)
        values = {
            "user_id": user_id,
            "requirement_id": requirement_id,
            "submission_type": submission_type,
            "phase_id": phase_id,
            "submitted_value": submitted_value,
            "extracted_username": extracted_username,
            "is_validated": is_validated,
            "validated_at": now if is_validated else None,
            "verification_completed": verification_completed,
            "updated_at": now,
        }

        # Use returning=True to get the row in a single round-trip
        submission = await upsert_on_conflict(
            db=self.db,
            model=Submission,
            values=values,
            index_elements=["user_id", "requirement_id"],
            update_fields=[
                "submission_type",
                "phase_id",
                "submitted_value",
                "extracted_username",
                "is_validated",
                "validated_at",
                "verification_completed",
                "updated_at",
            ],
            returning=True,
        )

        # After upsert with returning=True, the submission must exist
        if submission is None:
            raise RuntimeError("Upsert with returning=True returned no row")
        return submission

    async def get_last_submission_time(
        self,
        user_id: str,
        requirement_id: str,
    ) -> datetime | None:
        """Get the timestamp of the user's most recent completed verification.

        Used to enforce cooldown periods between verification attempts.
        Only considers submissions where verification actually ran (not blocked
        by server errors), so users aren't penalized for infrastructure issues.

        Args:
            user_id: The user's ID
            requirement_id: The requirement ID to check

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
