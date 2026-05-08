"""Repository for verification job status records."""

from uuid import UUID, uuid4

from sqlalchemy import select, text
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from learn_to_cloud_shared.models import (
    SubmissionType,
    VerificationJob,
    VerificationJobStatus,
    utcnow,
)

ACTIVE_JOB_STATUSES = (
    VerificationJobStatus.QUEUED,
    VerificationJobStatus.STARTING,
    VerificationJobStatus.RUNNING,
)
ACTIVE_JOB_STATUS_PREDICATE = "status IN ('queued', 'starting', 'running')"

TERMINAL_JOB_STATUSES = (
    VerificationJobStatus.SUCCEEDED,
    VerificationJobStatus.FAILED,
    VerificationJobStatus.SERVER_ERROR,
    VerificationJobStatus.CANCELLED,
)


class VerificationJobRepository:
    """Repository for verification job status records."""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def create(
        self,
        *,
        user_id: int,
        requirement_id: str,
        submission_type: SubmissionType,
        phase_id: int,
        submitted_value: str,
        extracted_username: str | None = None,
        cloud_provider: str | None = None,
        status: VerificationJobStatus = VerificationJobStatus.QUEUED,
        orchestration_instance_id: str | None = None,
        traceparent: str | None = None,
    ) -> VerificationJob:
        """Create a verification job and let DB constraints enforce uniqueness."""
        job = VerificationJob(
            id=uuid4(),
            user_id=user_id,
            requirement_id=requirement_id,
            phase_id=phase_id,
            submission_type=submission_type,
            submitted_value=submitted_value,
            extracted_username=extracted_username,
            cloud_provider=cloud_provider,
            status=status,
            orchestration_instance_id=orchestration_instance_id,
            traceparent=traceparent,
        )
        self.db.add(job)
        await self.db.flush()
        return job

    async def create_or_get_active(
        self,
        *,
        user_id: int,
        requirement_id: str,
        submission_type: SubmissionType,
        phase_id: int,
        submitted_value: str,
        extracted_username: str | None = None,
        cloud_provider: str | None = None,
        orchestration_instance_id: str | None = None,
        traceparent: str | None = None,
    ) -> tuple[VerificationJob, bool]:
        """Create a queued job, or return the active one for the requirement."""
        for _ in range(2):
            now = utcnow()
            stmt = (
                pg_insert(VerificationJob)
                .values(
                    id=uuid4(),
                    user_id=user_id,
                    requirement_id=requirement_id,
                    phase_id=phase_id,
                    submission_type=submission_type,
                    submitted_value=submitted_value,
                    extracted_username=extracted_username,
                    cloud_provider=cloud_provider,
                    status=VerificationJobStatus.QUEUED,
                    orchestration_instance_id=orchestration_instance_id,
                    traceparent=traceparent,
                    created_at=now,
                    updated_at=now,
                )
                .on_conflict_do_nothing(
                    index_elements=["user_id", "requirement_id"],
                    index_where=text(ACTIVE_JOB_STATUS_PREDICATE),
                )
                .returning(VerificationJob)
            )
            result = await self.db.execute(stmt)
            job = result.scalar_one_or_none()
            if job is not None:
                return job, True

            active_job = await self.get_active_for_requirement(user_id, requirement_id)
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
        requirement_id: str,
    ) -> VerificationJob | None:
        """Get the active job for a user and requirement, if one exists."""
        result = await self.db.execute(
            select(VerificationJob)
            .where(
                VerificationJob.user_id == user_id,
                VerificationJob.requirement_id == requirement_id,
                VerificationJob.status.in_(ACTIVE_JOB_STATUSES),
            )
            .order_by(VerificationJob.created_at.desc())
            .limit(1)
        )
        return result.scalar_one_or_none()

    async def get_active_for_phase(
        self,
        user_id: int,
        phase_id: int,
    ) -> list[VerificationJob]:
        """Get active jobs for a user in a phase."""
        result = await self.db.execute(
            select(VerificationJob)
            .where(
                VerificationJob.user_id == user_id,
                VerificationJob.phase_id == phase_id,
                VerificationJob.status.in_(ACTIVE_JOB_STATUSES),
            )
            .order_by(VerificationJob.created_at.desc())
        )
        return list(result.scalars().all())

    async def get_latest_for_requirement(
        self,
        user_id: int,
        requirement_id: str,
    ) -> VerificationJob | None:
        """Get the latest job for a user and requirement."""
        result = await self.db.execute(
            select(VerificationJob)
            .where(
                VerificationJob.user_id == user_id,
                VerificationJob.requirement_id == requirement_id,
            )
            .order_by(VerificationJob.created_at.desc())
            .limit(1)
        )
        return result.scalar_one_or_none()

    async def update_status(
        self,
        job_id: UUID,
        status: VerificationJobStatus,
        *,
        orchestration_instance_id: str | None = None,
        result_submission_id: int | None = None,
        error_code: str | None = None,
        error_message: str | None = None,
    ) -> VerificationJob | None:
        """Update a verification job status and lifecycle metadata."""
        job = await self.get_by_id(job_id)
        if job is None:
            return None

        now = utcnow()
        job.status = status
        job.updated_at = now
        if status in (VerificationJobStatus.STARTING, VerificationJobStatus.RUNNING):
            job.started_at = job.started_at or now
        if status in TERMINAL_JOB_STATUSES:
            job.completed_at = now
        if orchestration_instance_id is not None:
            job.orchestration_instance_id = orchestration_instance_id
        if result_submission_id is not None:
            job.result_submission_id = result_submission_id
        if error_code is not None:
            job.error_code = error_code
        if error_message is not None:
            job.error_message = error_message
        if status == VerificationJobStatus.SUCCEEDED:
            job.error_code = None
            job.error_message = None

        await self.db.flush()
        return job

    async def mark_starting(
        self,
        job_id: UUID,
        orchestration_instance_id: str,
    ) -> VerificationJob | None:
        """Mark a job as starting under an execution backend."""
        return await self.update_status(
            job_id,
            VerificationJobStatus.STARTING,
            orchestration_instance_id=orchestration_instance_id,
        )

    async def mark_running(self, job_id: UUID) -> VerificationJob | None:
        """Mark a job as running."""
        return await self.update_status(job_id, VerificationJobStatus.RUNNING)

    async def mark_succeeded(
        self,
        job_id: UUID,
        result_submission_id: int,
    ) -> VerificationJob | None:
        """Mark a job as succeeded with its persisted submission result."""
        return await self.update_status(
            job_id,
            VerificationJobStatus.SUCCEEDED,
            result_submission_id=result_submission_id,
        )

    async def mark_failed(
        self,
        job_id: UUID,
        *,
        error_code: str,
        error_message: str,
        result_submission_id: int | None = None,
    ) -> VerificationJob | None:
        """Mark a job as failed due to user-correctable validation failure."""
        return await self.update_status(
            job_id,
            VerificationJobStatus.FAILED,
            error_code=error_code,
            error_message=error_message,
            result_submission_id=result_submission_id,
        )

    async def mark_server_error(
        self,
        job_id: UUID,
        *,
        error_code: str,
        error_message: str,
        result_submission_id: int | None = None,
    ) -> VerificationJob | None:
        """Mark a job as failed due to verifier infrastructure or server error."""
        return await self.update_status(
            job_id,
            VerificationJobStatus.SERVER_ERROR,
            error_code=error_code,
            error_message=error_message,
            result_submission_id=result_submission_id,
        )

    async def mark_cancelled(
        self,
        job_id: UUID,
        *,
        error_code: str | None = None,
        error_message: str | None = None,
    ) -> VerificationJob | None:
        """Mark a job as cancelled."""
        return await self.update_status(
            job_id,
            VerificationJobStatus.CANCELLED,
            error_code=error_code,
            error_message=error_message,
        )
