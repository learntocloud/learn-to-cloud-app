"""Integration tests for persisted verification job execution."""

from unittest.mock import AsyncMock, patch
from uuid import UUID

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from learn_to_cloud_shared.models import (
    Submission,
    SubmissionType,
    VerificationJobStatus,
)
from learn_to_cloud_shared.repositories.submission_repository import (
    SubmissionRepository,
)
from learn_to_cloud_shared.repositories.user_repository import UserRepository
from learn_to_cloud_shared.repositories.verification_job_repository import (
    VerificationJobRepository,
)
from learn_to_cloud_shared.schemas import HandsOnRequirement, ValidationResult
from learn_to_cloud_shared.verification_job_executor import (
    REQUIREMENT_NOT_FOUND_ERROR_CODE,
    VALIDATION_FAILED_ERROR_CODE,
    VERIFICATION_INCOMPLETE_ERROR_CODE,
    execute_verification_job,
    persist_verification_result,
    prepare_verification_job,
    run_verification,
)

pytestmark = pytest.mark.integration

USER_ID = 82001
REQUIREMENT_ID = "verification-executor-test"


@pytest.fixture()
def session_maker(test_engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(
        bind=test_engine,
        class_=AsyncSession,
        expire_on_commit=False,
        autoflush=False,
    )


def _requirement(
    submission_type: SubmissionType = SubmissionType.CI_STATUS,
) -> HandsOnRequirement:
    return HandsOnRequirement(
        id=REQUIREMENT_ID,
        submission_type=submission_type,
        name="Verification Executor Test",
        description="Test requirement",
    )


async def _create_job(
    session_maker: async_sessionmaker[AsyncSession],
    *,
    submission_type: SubmissionType = SubmissionType.CI_STATUS,
) -> UUID:
    async with session_maker() as db:
        await UserRepository(db).upsert(
            USER_ID,
            github_username="executoruser",
        )
        job = await VerificationJobRepository(db).create(
            user_id=USER_ID,
            requirement_id=REQUIREMENT_ID,
            submission_type=submission_type,
            phase_id=3,
            submitted_value="https://github.com/executoruser/repo",
        )
        await db.commit()
        return job.id


async def _get_job_status(
    session_maker: async_sessionmaker[AsyncSession],
    job_id: UUID,
) -> tuple[VerificationJobStatus, int | None, str | None, str | None]:
    async with session_maker() as db:
        job = await VerificationJobRepository(db).get_by_id(job_id)
        assert job is not None
        return (
            job.status,
            job.result_submission_id,
            job.error_code,
            job.error_message,
        )


async def _get_submission(
    session_maker: async_sessionmaker[AsyncSession],
    submission_id: int,
) -> Submission:
    async with session_maker() as db:
        submission = await SubmissionRepository(db).get_by_user_and_requirement(
            USER_ID,
            REQUIREMENT_ID,
        )
        assert submission is not None
        assert submission.id == submission_id
        return submission


async def _count_submissions(
    session_maker: async_sessionmaker[AsyncSession],
) -> int:
    async with session_maker() as db:
        return await db.scalar(select(func.count()).select_from(Submission)) or 0


async def test_split_verification_primitives_prepare_run_and_persist(
    session_maker: async_sessionmaker[AsyncSession],
):
    job_id = await _create_job(session_maker)
    validation = AsyncMock(
        return_value=ValidationResult(is_valid=True, message="Verified")
    )

    with patch(
        "learn_to_cloud_shared.verification_job_executor.get_requirement_by_id",
        return_value=_requirement(),
    ):
        preparation = await prepare_verification_job(
            job_id,
            session_maker=session_maker,
        )

    assert preparation.terminal_result is None
    assert preparation.job is not None
    assert preparation.job.to_payload()["id"] == str(job_id)

    status, result_submission_id, error_code, error_message = await _get_job_status(
        session_maker,
        job_id,
    )
    assert status == VerificationJobStatus.RUNNING
    assert result_submission_id is None
    assert error_code is None
    assert error_message is None

    with patch(
        "learn_to_cloud_shared.verification_job_executor.validate_submission",
        validation,
    ):
        run_result = await run_verification(preparation.job)

    assert await _count_submissions(session_maker) == 0
    assert run_result.to_payload()["job"] == preparation.job.to_payload()

    result = await persist_verification_result(
        run_result,
        session_maker=session_maker,
    )

    assert result.status == VerificationJobStatus.SUCCEEDED
    assert result.submission_id is not None
    assert await _count_submissions(session_maker) == 1


async def test_execute_verification_job_marks_success_and_links_submission(
    session_maker: async_sessionmaker[AsyncSession],
):
    job_id = await _create_job(session_maker)
    validation = AsyncMock(
        return_value=ValidationResult(is_valid=True, message="Verified")
    )

    with (
        patch(
            "learn_to_cloud_shared.verification_job_executor.get_requirement_by_id",
            return_value=_requirement(),
        ),
        patch(
            "learn_to_cloud_shared.verification_job_executor.validate_submission",
            validation,
        ),
    ):
        result = await execute_verification_job(job_id, session_maker=session_maker)

    assert result.status == VerificationJobStatus.SUCCEEDED
    assert result.submission_id is not None
    assert result.is_valid is True
    assert result.verification_completed is True
    payload = result.to_payload()
    assert payload["status"] == "succeeded"
    assert payload["code"] == "verification_succeeded"
    assert payload["requirement_id"] == REQUIREMENT_ID
    assert payload["requirement_name"] == "Verification Executor Test"
    assert payload["submission_type"] == SubmissionType.CI_STATUS.value
    assert payload["message"] == "Verification succeeded."
    assert payload["detail"] == "Verified"

    status, result_submission_id, error_code, error_message = await _get_job_status(
        session_maker,
        job_id,
    )
    assert status == VerificationJobStatus.SUCCEEDED
    assert result_submission_id == result.submission_id
    assert error_code is None
    assert error_message is None

    submission = await _get_submission(session_maker, result.submission_id)
    assert submission.is_validated is True
    assert submission.verification_completed is True
    assert submission.extracted_username == "executoruser"

    validation.assert_awaited_once()
    assert validation.await_args.kwargs["expected_username"] == "executoruser"


async def test_execute_verification_job_marks_user_validation_failure(
    session_maker: async_sessionmaker[AsyncSession],
):
    job_id = await _create_job(session_maker)
    validation = AsyncMock(
        return_value=ValidationResult(
            is_valid=False,
            message="Fix your repository settings.",
            verification_completed=True,
        )
    )

    with (
        patch(
            "learn_to_cloud_shared.verification_job_executor.get_requirement_by_id",
            return_value=_requirement(),
        ),
        patch(
            "learn_to_cloud_shared.verification_job_executor.validate_submission",
            validation,
        ),
    ):
        result = await execute_verification_job(job_id, session_maker=session_maker)

    assert result.status == VerificationJobStatus.FAILED
    assert result.submission_id is not None
    assert result.is_valid is False
    assert result.verification_completed is True
    assert result.code == VALIDATION_FAILED_ERROR_CODE
    assert result.message == "Verification failed."
    assert result.detail == "Fix your repository settings."

    status, result_submission_id, error_code, error_message = await _get_job_status(
        session_maker,
        job_id,
    )
    assert status == VerificationJobStatus.FAILED
    assert result_submission_id == result.submission_id
    assert error_code == VALIDATION_FAILED_ERROR_CODE
    assert error_message == "Fix your repository settings."

    submission = await _get_submission(session_maker, result.submission_id)
    assert submission.is_validated is False
    assert submission.verification_completed is True
    assert submission.validation_message == "Fix your repository settings."


async def test_execute_verification_job_marks_server_error(
    session_maker: async_sessionmaker[AsyncSession],
):
    job_id = await _create_job(session_maker)
    validation = AsyncMock(
        return_value=ValidationResult(
            is_valid=False,
            message="GitHub API unavailable.",
            verification_completed=False,
        )
    )

    with (
        patch(
            "learn_to_cloud_shared.verification_job_executor.get_requirement_by_id",
            return_value=_requirement(),
        ),
        patch(
            "learn_to_cloud_shared.verification_job_executor.validate_submission",
            validation,
        ),
    ):
        result = await execute_verification_job(job_id, session_maker=session_maker)

    assert result.status == VerificationJobStatus.SERVER_ERROR
    assert result.submission_id is not None
    assert result.is_valid is False
    assert result.verification_completed is False
    assert result.code == VERIFICATION_INCOMPLETE_ERROR_CODE
    assert result.message == "Verification could not be completed."
    assert result.detail == "GitHub API unavailable."

    status, result_submission_id, error_code, error_message = await _get_job_status(
        session_maker,
        job_id,
    )
    assert status == VerificationJobStatus.SERVER_ERROR
    assert result_submission_id == result.submission_id
    assert error_code == VERIFICATION_INCOMPLETE_ERROR_CODE
    assert error_message == "GitHub API unavailable."

    submission = await _get_submission(session_maker, result.submission_id)
    assert submission.is_validated is False
    assert submission.verification_completed is False
    assert submission.validation_message == "GitHub API unavailable."


async def test_execute_verification_job_is_idempotent_for_terminal_jobs(
    session_maker: async_sessionmaker[AsyncSession],
):
    job_id = await _create_job(session_maker)
    async with session_maker() as db:
        submission = await SubmissionRepository(db).create(
            user_id=USER_ID,
            requirement_id=REQUIREMENT_ID,
            submission_type=SubmissionType.CI_STATUS,
            phase_id=3,
            submitted_value="https://github.com/executoruser/repo",
            extracted_username="executoruser",
            is_validated=True,
        )
        updated = await VerificationJobRepository(db).mark_succeeded(
            job_id,
            submission.id,
        )
        assert updated is not None
        await db.commit()

    validation = AsyncMock()
    with patch(
        "learn_to_cloud_shared.verification_job_executor.validate_submission",
        validation,
    ):
        result = await execute_verification_job(job_id, session_maker=session_maker)

    assert result.status == VerificationJobStatus.SUCCEEDED
    assert result.submission_id == submission.id
    assert result.code == "verification_succeeded"
    assert result.message == "Verification succeeded."
    assert await _count_submissions(session_maker) == 1
    validation.assert_not_awaited()


async def test_execute_verification_job_marks_missing_requirement_server_error(
    session_maker: async_sessionmaker[AsyncSession],
):
    job_id = await _create_job(session_maker)
    validation = AsyncMock()

    with (
        patch(
            "learn_to_cloud_shared.verification_job_executor.get_requirement_by_id",
            return_value=None,
        ),
        patch(
            "learn_to_cloud_shared.verification_job_executor.validate_submission",
            validation,
        ),
    ):
        result = await execute_verification_job(job_id, session_maker=session_maker)

    assert result.status == VerificationJobStatus.SERVER_ERROR
    assert result.submission_id is None
    assert result.verification_completed is False
    assert result.code == REQUIREMENT_NOT_FOUND_ERROR_CODE
    assert result.message == "Verification could not be completed."
    assert result.detail == f"Requirement not found: {REQUIREMENT_ID}"

    status, result_submission_id, error_code, error_message = await _get_job_status(
        session_maker,
        job_id,
    )
    assert status == VerificationJobStatus.SERVER_ERROR
    assert result_submission_id is None
    assert error_code == REQUIREMENT_NOT_FOUND_ERROR_CODE
    assert error_message == f"Requirement not found: {REQUIREMENT_ID}"
    assert await _count_submissions(session_maker) == 0
    validation.assert_not_awaited()
