"""Integration tests for VerificationJobRepository."""

from uuid import UUID

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from learn_to_cloud_shared.models import (
    SubmissionType,
    VerificationJob,
    VerificationJobStatus,
)
from learn_to_cloud_shared.repositories.submission_repository import (
    SubmissionRepository,
)
from learn_to_cloud_shared.repositories.user_repository import UserRepository
from learn_to_cloud_shared.repositories.verification_job_repository import (
    VerificationJobRepository,
)

pytestmark = pytest.mark.integration

USER_ID = 81001


@pytest.fixture()
async def user(db_session: AsyncSession):
    """Create a test user for FK constraints."""
    repo = UserRepository(db_session)
    return await repo.upsert(USER_ID, github_username="verificationjobuser")


async def _create_job(
    repo: VerificationJobRepository,
    *,
    requirement_id: str = "req-1",
):
    return await repo.create(
        user_id=USER_ID,
        requirement_id=requirement_id,
        submission_type=SubmissionType.GITHUB_PROFILE,
        phase_id=0,
        submitted_value="https://github.com/testuser",
        extracted_username="testuser",
        traceparent="00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01",
    )


class TestCreate:
    async def test_creates_verification_job(
        self,
        db_session: AsyncSession,
        user,
    ):
        repo = VerificationJobRepository(db_session)

        job = await _create_job(repo)

        assert isinstance(job.id, UUID)
        assert job.status == VerificationJobStatus.QUEUED
        assert job.user_id == USER_ID
        assert job.requirement_id == "req-1"
        assert job.submission_type == SubmissionType.GITHUB_PROFILE
        assert job.traceparent is not None
        assert job.created_at is not None

    async def test_create_or_get_active_returns_existing_active_job(
        self,
        db_session: AsyncSession,
        user,
    ):
        repo = VerificationJobRepository(db_session)

        first, first_created = await repo.create_or_get_active(
            user_id=USER_ID,
            requirement_id="req-active",
            submission_type=SubmissionType.CTF_TOKEN,
            phase_id=1,
            submitted_value="token-1",
        )
        second, second_created = await repo.create_or_get_active(
            user_id=USER_ID,
            requirement_id="req-active",
            submission_type=SubmissionType.CTF_TOKEN,
            phase_id=1,
            submitted_value="token-2",
        )

        assert first_created is True
        assert second_created is False
        assert second.id == first.id
        assert second.submitted_value == "token-1"

        count = await db_session.scalar(
            select(func.count()).select_from(VerificationJob)
        )
        assert count == 1

    async def test_terminal_job_allows_new_active_job(
        self,
        db_session: AsyncSession,
        user,
    ):
        repo = VerificationJobRepository(db_session)

        first, first_created = await repo.create_or_get_active(
            user_id=USER_ID,
            requirement_id="req-retry",
            submission_type=SubmissionType.CTF_TOKEN,
            phase_id=1,
            submitted_value="token-1",
        )
        await repo.mark_failed(
            first.id,
            error_code="validation_failed",
            error_message="Try again",
        )
        second, second_created = await repo.create_or_get_active(
            user_id=USER_ID,
            requirement_id="req-retry",
            submission_type=SubmissionType.CTF_TOKEN,
            phase_id=1,
            submitted_value="token-2",
        )

        assert first_created is True
        assert second_created is True
        assert second.id != first.id
        assert second.submitted_value == "token-2"


class TestFind:
    async def test_gets_active_and_latest_jobs(
        self,
        db_session: AsyncSession,
        user,
    ):
        repo = VerificationJobRepository(db_session)
        first = await _create_job(repo, requirement_id="req-latest")
        await repo.mark_cancelled(first.id, error_code="user_cancelled")
        second = await _create_job(repo, requirement_id="req-latest")

        active = await repo.get_active_for_requirement(USER_ID, "req-latest")
        latest = await repo.get_latest_for_requirement(USER_ID, "req-latest")

        assert active is not None
        assert active.id == second.id
        assert latest is not None
        assert latest.id == second.id

    async def test_returns_none_for_missing_job(
        self,
        db_session: AsyncSession,
        user,
    ):
        repo = VerificationJobRepository(db_session)

        result = await repo.get_latest_for_requirement(USER_ID, "missing")

        assert result is None


class TestStatusTransitions:
    async def test_marks_starting_and_running(
        self,
        db_session: AsyncSession,
        user,
    ):
        repo = VerificationJobRepository(db_session)
        job = await _create_job(repo)

        starting = await repo.mark_starting(job.id, "durable-instance-1")
        assert starting is not None
        assert starting.status == VerificationJobStatus.STARTING
        assert starting.orchestration_instance_id == "durable-instance-1"
        assert starting.started_at is not None

        running = await repo.mark_running(job.id)

        assert running is not None
        assert running.status == VerificationJobStatus.RUNNING
        assert running.started_at == starting.started_at

    async def test_marks_succeeded_with_submission_result(
        self,
        db_session: AsyncSession,
        user,
    ):
        job_repo = VerificationJobRepository(db_session)
        submission_repo = SubmissionRepository(db_session)
        job = await _create_job(job_repo)
        submission = await submission_repo.create(
            user_id=USER_ID,
            requirement_id="req-1",
            submission_type=SubmissionType.GITHUB_PROFILE,
            phase_id=0,
            submitted_value="https://github.com/testuser",
            extracted_username="testuser",
            is_validated=True,
        )

        updated = await job_repo.mark_succeeded(job.id, submission.id)

        assert updated is not None
        assert updated.status == VerificationJobStatus.SUCCEEDED
        assert updated.result_submission_id == submission.id
        assert updated.error_code is None
        assert updated.error_message is None
        assert updated.completed_at is not None

    async def test_marks_server_error_with_error_details(
        self,
        db_session: AsyncSession,
        user,
    ):
        repo = VerificationJobRepository(db_session)
        job = await _create_job(repo)

        updated = await repo.mark_server_error(
            job.id,
            error_code="github_unavailable",
            error_message="GitHub API unavailable",
        )

        assert updated is not None
        assert updated.status == VerificationJobStatus.SERVER_ERROR
        assert updated.error_code == "github_unavailable"
        assert updated.error_message == "GitHub API unavailable"
        assert updated.completed_at is not None
