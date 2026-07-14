"""Repository for verification job records.

After Phase D.3 (#465) the table references the curriculum solely via
``requirement_uuid`` (FK to ``requirements.uuid``). Repo methods speak
UUIDs; callers translate to/from human-readable requirement ids at
the boundary.

PR4 stripped the legacy status enum and the ``mark_*`` lifecycle
methods. ``VerificationJob`` is now a thin work-queue marker: a row
exists during in-flight verification work, gets linked to a
``Submission`` via :meth:`VerificationJobRepository.link_submission`
when the persist activity completes, and is deleted by the poller on
Durable terminal failure via
:meth:`VerificationJobRepository.delete_active`.
"""

from __future__ import annotations

from collections.abc import Iterable
from enum import StrEnum
from uuid import UUID, uuid4

from sqlalchemy import delete, select, text, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from learn_to_cloud_shared.models import VerificationJob, utcnow
from learn_to_cloud_shared.submission_values import SubmittedValue

ACTIVE_JOB_UNLINKED_PREDICATE = "result_submission_id IS NULL"


class LinkResult(StrEnum):
    """Outcome of :meth:`VerificationJobRepository.link_submission`."""

    LINKED = "linked"
    ALREADY_LINKED = "already_linked"
    MISSING = "missing"


class VerificationJobRepository:
    """Repository for verification job records."""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def create(
        self,
        *,
        user_id: int,
        requirement_uuid: UUID,
        submitted_value: SubmittedValue,
        extracted_username: str | None = None,
        cloud_provider: str | None = None,
        traceparent: str | None = None,
        id: UUID | None = None,
    ) -> VerificationJob:
        """Create a verification job and let DB constraints enforce uniqueness.

        ``id`` lets a caller share the id of an already-created
        ``verification_attempts`` row (the unified-attempt submission path);
        omit it to generate a fresh id (the legacy job-only path).
        """
        value_columns = submitted_value.to_columns()
        job = VerificationJob(
            id=id or uuid4(),
            user_id=user_id,
            requirement_uuid=requirement_uuid,
            **value_columns,
            extracted_username=extracted_username,
            cloud_provider=cloud_provider,
            traceparent=traceparent,
        )
        self.db.add(job)
        await self.db.flush()
        return job

    async def create_or_get_active(
        self,
        *,
        user_id: int,
        requirement_uuid: UUID,
        submitted_value: SubmittedValue,
        extracted_username: str | None = None,
        cloud_provider: str | None = None,
        traceparent: str | None = None,
    ) -> tuple[VerificationJob, bool]:
        """Create a queued job, or return the active one for the requirement.

        The partial unique index
        ``uq_verification_jobs_active_user_req_uuid`` ensures only one
        row per ``(user_id, requirement_uuid)`` may be unlinked at a
        time. A brand-new row has ``result_submission_id=NULL`` so it
        falls under the predicate; once the persist activity links a
        Submission the row exits and a follow-up submit succeeds.
        """
        for _ in range(2):
            now = utcnow()
            stmt = (
                pg_insert(VerificationJob)
                .values(
                    id=uuid4(),
                    user_id=user_id,
                    requirement_uuid=requirement_uuid,
                    **submitted_value.to_columns(),
                    extracted_username=extracted_username,
                    cloud_provider=cloud_provider,
                    traceparent=traceparent,
                    created_at=now,
                    updated_at=now,
                )
                .on_conflict_do_nothing(
                    index_elements=["user_id", "requirement_uuid"],
                    index_where=text(ACTIVE_JOB_UNLINKED_PREDICATE),
                )
                .returning(VerificationJob)
            )
            result = await self.db.execute(stmt)
            job = result.scalar_one_or_none()
            if job is not None:
                return job, True

            active_job = await self.get_active_for_requirement(
                user_id, requirement_uuid
            )
            if active_job is not None:
                return active_job, False

        raise RuntimeError("Could not resolve active verification job conflict")

    async def get_by_id(self, job_id: UUID) -> VerificationJob | None:
        """Get a verification job by ID."""
        result = await self.db.execute(
            select(VerificationJob).where(VerificationJob.id == job_id)
        )
        return result.scalar_one_or_none()

    async def get_active_for_requirement(
        self,
        user_id: int,
        requirement_uuid: UUID,
    ) -> VerificationJob | None:
        """Get the active (unlinked) job for a user and requirement, if any."""
        result = await self.db.execute(
            select(VerificationJob)
            .where(
                VerificationJob.user_id == user_id,
                VerificationJob.requirement_uuid == requirement_uuid,
                VerificationJob.result_submission_id.is_(None),
            )
            .order_by(VerificationJob.created_at.desc())
            .limit(1)
        )
        return result.scalar_one_or_none()

    async def get_active_for_requirements(
        self,
        user_id: int,
        requirement_uuids: Iterable[UUID],
    ) -> list[VerificationJob]:
        """Get active (unlinked) jobs for a user across a set of requirements.

        Replaces ``get_active_for_phase`` -- callers now resolve a phase
        to its requirement UUIDs (typically from the in-memory phase
        tree) and pass them explicitly.
        """
        uuids = list(requirement_uuids)
        if not uuids:
            return []

        result = await self.db.execute(
            select(VerificationJob)
            .where(
                VerificationJob.user_id == user_id,
                VerificationJob.requirement_uuid.in_(uuids),
                VerificationJob.result_submission_id.is_(None),
            )
            .order_by(VerificationJob.created_at.desc())
        )
        return list(result.scalars().all())

    async def get_latest_for_requirement(
        self,
        user_id: int,
        requirement_uuid: UUID,
    ) -> VerificationJob | None:
        """Get the latest job for a user and requirement."""
        result = await self.db.execute(
            select(VerificationJob)
            .where(
                VerificationJob.user_id == user_id,
                VerificationJob.requirement_uuid == requirement_uuid,
            )
            .order_by(VerificationJob.created_at.desc())
            .limit(1)
        )
        return result.scalar_one_or_none()

    async def link_submission(
        self,
        job_id: UUID,
        submission_id: int,
    ) -> LinkResult:
        """Link a persisted ``Submission`` to this verification job.

        Idempotent against Durable activity retries: only links when the
        row is still unlinked. On rowcount=0 re-reads to distinguish the
        "another activity attempt linked it first" case from the
        "poller already deleted the row" case.
        """
        stmt = (
            update(VerificationJob)
            .where(
                VerificationJob.id == job_id,
                VerificationJob.result_submission_id.is_(None),
            )
            .values(
                result_submission_id=submission_id,
                updated_at=utcnow(),
            )
        )
        result = await self.db.execute(stmt)
        rowcount = getattr(result, "rowcount", 0) or 0
        if rowcount > 0:
            return LinkResult.LINKED

        existing = await self.get_by_id(job_id)
        if existing is None:
            return LinkResult.MISSING
        return LinkResult.ALREADY_LINKED

    async def delete_active(self, job_id: UUID) -> bool:
        """Delete an active, unlinked verification job by id.

        Guards against racing the persist activity: deletion only runs
        when the row still has no linked Submission. If persist won the
        race the delete is a no-op and the caller learns via the
        returned ``False``.
        """
        stmt = delete(VerificationJob).where(
            VerificationJob.id == job_id,
            VerificationJob.result_submission_id.is_(None),
        )
        result = await self.db.execute(stmt)
        rowcount = getattr(result, "rowcount", 0) or 0
        return rowcount > 0
