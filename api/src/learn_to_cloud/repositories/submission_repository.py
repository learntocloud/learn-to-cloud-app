"""Submission repository for hands-on validation database operations."""

from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from learn_to_cloud.models import Submission, SubmissionType


class SubmissionRepository:
    """Repository for Submission database operations."""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def get_by_user_and_phase(
        self, user_id: int, phase_id: int
    ) -> list[Submission]:
        """Get the latest submission per requirement for a user in a phase."""
        latest_sq = (
            select(
                Submission.requirement_id,
                func.max(Submission.id).label("max_id"),
            )
            .where(
                Submission.user_id == user_id,
                Submission.phase_id == phase_id,
            )
            .group_by(Submission.requirement_id)
            .subquery()
        )
        result = await self.db.execute(
            select(Submission).join(
                latest_sq,
                (Submission.id == latest_sq.c.max_id),
            )
        )
        return list(result.scalars().all())

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
            .order_by(Submission.id.desc())
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
                Set to False when blocked by server errors (e.g., GitHub API down).
                Only completed verifications count toward the daily cap.
            feedback_json: JSON-serialized task feedback for multi-task submissions.
            cloud_provider: Cloud provider slug ("aws", "azure", "gcp") for
                multi-cloud labs. None for non-multi-cloud submissions.
        """
        now = datetime.now(UTC)

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

    async def are_all_requirements_validated(
        self, user_id: int, requirement_ids: list[str]
    ) -> bool:
        """Check if the user has validated ALL of the given requirements.

        Used for sequential phase gating — ensures prior phase verification
        is fully complete before allowing the next phase's submissions.
        """
        if not requirement_ids:
            return True

        result = await self.db.execute(
            select(func.count(func.distinct(Submission.requirement_id))).where(
                Submission.user_id == user_id,
                Submission.requirement_id.in_(requirement_ids),
                Submission.is_validated.is_(True),
            )
        )
        validated_count = result.scalar_one() or 0
        return validated_count >= len(requirement_ids)

    async def get_validated_requirement_ids(self, user_id: int) -> set[str]:
        """Get all distinct requirement IDs with at least one validated submission.

        Used by progress computation to count hands-on completions
        directly from the source of truth (submissions table).
        """
        result = await self.db.execute(
            select(func.distinct(Submission.requirement_id)).where(
                Submission.user_id == user_id,
                Submission.is_validated.is_(True),
            )
        )
        return set(result.scalars().all())

    async def count_validated_for_requirements(
        self, user_id: int, requirement_ids: set[str]
    ) -> int:
        """Count how many of the given requirement IDs have been validated.

        Filters against a specific set of requirement IDs (from current content)
        to prevent stale/removed requirements from inflating counts.
        """
        if not requirement_ids:
            return 0
        result = await self.db.execute(
            select(func.count(func.distinct(Submission.requirement_id))).where(
                Submission.user_id == user_id,
                Submission.requirement_id.in_(requirement_ids),
                Submission.is_validated.is_(True),
            )
        )
        return result.scalar_one() or 0

    async def find_validated_by_value_in_phase(
        self,
        user_id: int,
        phase_id: int,
        submitted_value: str,
        exclude_requirement_id: str,
    ) -> str | None:
        """Find a validated submission with the same value in the same phase.

        Used to enforce PR uniqueness: the same PR URL cannot be used for
        multiple requirements within a phase.

        Returns:
            The requirement_id of the conflicting submission, or None.
        """
        result = await self.db.execute(
            select(Submission.requirement_id)
            .where(
                Submission.user_id == user_id,
                Submission.phase_id == phase_id,
                Submission.submitted_value == submitted_value,
                Submission.requirement_id != exclude_requirement_id,
                Submission.is_validated.is_(True),
            )
            .limit(1)
        )
        return result.scalar_one_or_none()
