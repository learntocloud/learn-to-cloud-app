"""Submission repository for hands-on validation database operations.

After Phase D.2 of #461 / #465 the table references the curriculum via
``requirement_uuid`` (FK to ``requirements.uuid``). All public methods
speak UUIDs; callers translate to/from the human-readable requirement
ids at the boundary (templates and DTOs).
"""

from collections.abc import Iterable
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from learn_to_cloud_shared.models import Submission, utcnow


class SubmissionRepository:
    """Repository for Submission database operations."""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def get_latest_for_requirements(
        self, user_id: int, requirement_uuids: Iterable[UUID]
    ) -> list[Submission]:
        """Get the latest submission per requirement_uuid for a user.

        Replaces the previous ``get_by_user_and_phase`` -- callers now
        pass an explicit list of requirement UUIDs (derived from a
        phase's hands-on requirements) instead of an int ``phase_id``.
        """
        uuids = list(requirement_uuids)
        if not uuids:
            return []

        latest_sq = (
            select(
                Submission.requirement_uuid,
                func.max(Submission.id).label("max_id"),
            )
            .where(
                Submission.user_id == user_id,
                Submission.requirement_uuid.in_(uuids),
            )
            .group_by(Submission.requirement_uuid)
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
        self, user_id: int, requirement_uuid: UUID
    ) -> Submission | None:
        """Get the latest submission for a user and requirement."""
        result = await self.db.execute(
            select(Submission)
            .where(
                Submission.user_id == user_id,
                Submission.requirement_uuid == requirement_uuid,
            )
            .order_by(Submission.id.desc())
            .limit(1)
        )
        return result.scalar_one_or_none()

    async def get_by_id(self, submission_id: int) -> Submission | None:
        """Get a submission by ID."""
        result = await self.db.execute(
            select(Submission).where(Submission.id == submission_id)
        )
        return result.scalar_one_or_none()

    async def create(
        self,
        user_id: int,
        requirement_uuid: UUID,
        submitted_value: str,
        extracted_username: str | None,
        is_validated: bool,
        verification_completed: bool = True,
        feedback_json: list[dict] | None = None,
        validation_message: str | None = None,
        cloud_provider: str | None = None,
    ) -> Submission:
        """Create a new submission row.

        Args:
            verification_completed: Whether the verification logic actually ran.
                Set to False when blocked by server errors (e.g., GitHub API down).
                Only completed verifications count toward the daily cap.
            feedback_json: Structured per-task feedback for multi-task
                submissions (list of TaskResult dicts). Persisted as JSONB.
            cloud_provider: Cloud provider slug ("aws", "azure", "gcp") for
                multi-cloud labs. None for non-multi-cloud submissions.
        """
        now = utcnow()
        submission = Submission(
            user_id=user_id,
            requirement_uuid=requirement_uuid,
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
        self, user_id: int, requirement_uuids: Iterable[UUID]
    ) -> bool:
        """Check if the user has validated ALL of the given requirements.

        Used for sequential phase gating -- ensures prior phase verification
        is fully complete before allowing the next phase's submissions.
        """
        uuids = list(requirement_uuids)
        if not uuids:
            return True

        result = await self.db.execute(
            select(func.count(func.distinct(Submission.requirement_uuid))).where(
                Submission.user_id == user_id,
                Submission.requirement_uuid.in_(uuids),
                Submission.is_validated.is_(True),
            )
        )
        validated_count = result.scalar_one() or 0
        return validated_count >= len(uuids)

    async def get_validated_requirement_uuids(self, user_id: int) -> set[UUID]:
        """Get all requirement UUIDs with at least one validated submission.

        Used by progress computation to count hands-on completions
        directly from the source of truth (submissions table).
        """
        result = await self.db.execute(
            select(func.distinct(Submission.requirement_uuid)).where(
                Submission.user_id == user_id,
                Submission.is_validated.is_(True),
            )
        )
        return set(result.scalars().all())

    async def count_validated_for_requirements(
        self, user_id: int, requirement_uuids: Iterable[UUID]
    ) -> int:
        """Count how many of the given requirement UUIDs have been validated.

        Filters against a specific set of UUIDs (from current content)
        so removed requirements never inflate counts.
        """
        uuids = list(requirement_uuids)
        if not uuids:
            return 0
        result = await self.db.execute(
            select(func.count(func.distinct(Submission.requirement_uuid))).where(
                Submission.user_id == user_id,
                Submission.requirement_uuid.in_(uuids),
                Submission.is_validated.is_(True),
            )
        )
        return result.scalar_one() or 0
