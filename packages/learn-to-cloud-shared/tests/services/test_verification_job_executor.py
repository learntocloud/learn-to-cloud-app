"""Integration tests for persisted verification job execution."""

from unittest.mock import AsyncMock, patch
from uuid import UUID

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from learn_to_cloud_shared.models import Submission, SubmissionType, VerificationJob
from learn_to_cloud_shared.repositories.user_repository import UserRepository
from learn_to_cloud_shared.repositories.verification_job_repository import (
    VerificationJobRepository,
)
from learn_to_cloud_shared.schemas import HandsOnRequirement, ValidationResult
from learn_to_cloud_shared.verification.execution import MAX_VALIDATION_MESSAGE_LENGTH
from learn_to_cloud_shared.verification_job_executor import (
    REQUIREMENT_NOT_FOUND_ERROR_CODE,
    VALIDATION_FAILED_ERROR_CODE,
    VERIFICATION_INCOMPLETE_ERROR_CODE,
    VERIFICATION_SUCCEEDED_CODE,
    PreparedVerificationJob,
    VerificationJobNotFoundError,
    VerificationRunResult,
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


async def _get_job_link(
    session_maker: async_sessionmaker[AsyncSession],
    job_id: UUID,
) -> int | None:
    """Return ``result_submission_id`` for the job, or ``None`` if missing.

    Asserts the row exists; tests for "row deleted" outcomes should query
    differently.
    """
    async with session_maker() as db:
        job = await VerificationJobRepository(db).get_by_id(job_id)
        assert job is not None
        return job.result_submission_id


async def _count_jobs(
    session_maker: async_sessionmaker[AsyncSession],
) -> int:
    async with session_maker() as db:
        return await db.scalar(select(func.count()).select_from(VerificationJob)) or 0


async def _count_submissions(
    session_maker: async_sessionmaker[AsyncSession],
) -> int:
    async with session_maker() as db:
        return await db.scalar(select(func.count()).select_from(Submission)) or 0


async def _get_submission(
    session_maker: async_sessionmaker[AsyncSession],
    submission_id: int,
) -> Submission:
    async with session_maker() as db:
        submission = await db.get(Submission, submission_id)
        assert submission is not None
        return submission


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

    assert result.status == "succeeded"
    assert result.code == VERIFICATION_SUCCEEDED_CODE
    assert result.submission_id is not None
    assert await _count_submissions(session_maker) == 1
    assert await _get_job_link(session_maker, job_id) == result.submission_id


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

    assert result.status == "succeeded"
    assert result.submission_id is not None
    assert result.is_valid is True
    assert result.verification_completed is True
    payload = result.to_payload()
    assert payload["status"] == "succeeded"
    assert payload["code"] == VERIFICATION_SUCCEEDED_CODE
    assert payload["requirement_id"] == REQUIREMENT_ID
    assert payload["requirement_name"] == "Verification Executor Test"
    assert payload["submission_type"] == SubmissionType.CI_STATUS.value
    assert payload["message"] == "Verification succeeded."
    # On success there is no validation message; ``detail`` is None.
    assert payload["detail"] is None

    assert await _get_job_link(session_maker, job_id) == result.submission_id
    submission = await _get_submission(session_maker, result.submission_id)
    assert submission.is_validated is True


async def test_execute_verification_job_marks_user_validation_failure(
    session_maker: async_sessionmaker[AsyncSession],
):
    job_id = await _create_job(session_maker)
    validation = AsyncMock(
        return_value=ValidationResult(
            is_valid=False,
            message="GitHub username does not match",
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

    assert result.status == "failed"
    assert result.code == VALIDATION_FAILED_ERROR_CODE
    assert result.is_valid is False
    assert result.verification_completed is True
    assert result.detail == "GitHub username does not match"

    assert await _get_job_link(session_maker, job_id) == result.submission_id


async def test_execute_verification_job_marks_server_error(
    session_maker: async_sessionmaker[AsyncSession],
):
    """A validator returning ``verification_completed=False`` records a
    server-error result. The Submission row exists and is linked but
    is_validated=False / verification_completed=False."""
    job_id = await _create_job(session_maker)
    validation = AsyncMock(
        return_value=ValidationResult(
            is_valid=False,
            message="GitHub API unavailable",
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

    assert result.status == "server_error"
    assert result.code == VERIFICATION_INCOMPLETE_ERROR_CODE
    assert result.verification_completed is False
    assert result.detail == "GitHub API unavailable"

    submission = await _get_submission(session_maker, result.submission_id)
    assert submission.is_validated is False
    assert submission.verification_completed is False


async def test_execute_verification_job_truncates_persisted_error_messages(
    session_maker: async_sessionmaker[AsyncSession],
):
    """Validation messages over the persisted limit are truncated for
    storage; the ``detail`` in the activity result follows the same
    rule."""
    job_id = await _create_job(session_maker)
    long_message = "x" * (MAX_VALIDATION_MESSAGE_LENGTH + 64)
    validation = AsyncMock(
        return_value=ValidationResult(
            is_valid=False,
            message=long_message,
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

    assert result.status == "failed"
    assert result.detail is not None
    assert len(result.detail) <= MAX_VALIDATION_MESSAGE_LENGTH


async def test_execute_verification_job_marks_missing_requirement_server_error(
    session_maker: async_sessionmaker[AsyncSession],
):
    """When the requirement vanishes from content between submit and
    execute, the executor writes a server-error Submission, links it,
    and short-circuits via the terminal_result path.

    Linking (rather than deleting the job row) keeps the executor
    idempotent on Durable activity retry — the second attempt sees the
    linked row and returns the same result."""
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

    assert result.status == "server_error"
    assert result.submission_id is not None
    assert result.verification_completed is False
    assert result.code == REQUIREMENT_NOT_FOUND_ERROR_CODE
    assert result.message == "Verification could not be completed."
    assert result.detail == f"Requirement not found: {REQUIREMENT_ID}"

    # Row stays linked so a retry is idempotent.
    assert await _get_job_link(session_maker, job_id) == result.submission_id
    submission = await _get_submission(session_maker, result.submission_id)
    assert submission.is_validated is False
    assert submission.verification_completed is False
    assert submission.validation_message == f"Requirement not found: {REQUIREMENT_ID}"

    validation.assert_not_awaited()


async def test_execute_verification_job_is_idempotent_for_terminal_jobs(
    session_maker: async_sessionmaker[AsyncSession],
):
    """The replay short-circuit fires when the job already has a linked
    Submission; the result is reconstructed from that Submission rather
    than running the validator again."""
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
        first = await execute_verification_job(job_id, session_maker=session_maker)
        # Reset the validator so the retry would clearly be observable
        # if the short-circuit weren't in place.
        validation.reset_mock()
        second = await execute_verification_job(job_id, session_maker=session_maker)

    assert first.status == "succeeded"
    assert second.status == "succeeded"
    assert second.submission_id == first.submission_id
    assert await _count_submissions(session_maker) == 1
    validation.assert_not_awaited()


async def test_persist_is_idempotent_via_result_submission_id_guard(
    session_maker: async_sessionmaker[AsyncSession],
):
    """A second ``persist_verification_result`` call after the first one
    linked a Submission must short-circuit on the result_submission_id
    guard, not write a duplicate row."""
    job_id = await _create_job(session_maker)

    prepared = PreparedVerificationJob(
        id=job_id,
        user_id=USER_ID,
        github_username="executoruser",
        requirement=_requirement(),
        phase_id=3,
        submitted_value="https://github.com/executoruser/repo",
    )
    run_result = VerificationRunResult(
        job=prepared,
        validation_result=ValidationResult(is_valid=True, message="Verified"),
    )

    first = await persist_verification_result(
        run_result,
        session_maker=session_maker,
    )
    second = await persist_verification_result(
        run_result,
        session_maker=session_maker,
    )

    assert first.status == "succeeded"
    assert second.status == "succeeded"
    assert second.submission_id == first.submission_id
    assert await _count_submissions(session_maker) == 1


async def test_persist_raises_when_job_row_was_deleted(
    session_maker: async_sessionmaker[AsyncSession],
):
    """If the poller's ``delete_active`` won the race the persist
    activity raises ``VerificationJobNotFoundError`` rather than
    creating an orphan Submission."""
    job_id = await _create_job(session_maker)

    # Simulate the poller having deleted the row mid-flight.
    async with session_maker() as db:
        deleted = await VerificationJobRepository(db).delete_active(job_id)
        await db.commit()
        assert deleted is True

    prepared = PreparedVerificationJob(
        id=job_id,
        user_id=USER_ID,
        github_username="executoruser",
        requirement=_requirement(),
        phase_id=3,
        submitted_value="https://github.com/executoruser/repo",
    )
    run_result = VerificationRunResult(
        job=prepared,
        validation_result=ValidationResult(is_valid=True, message="Verified"),
    )

    with pytest.raises(VerificationJobNotFoundError):
        await persist_verification_result(
            run_result,
            session_maker=session_maker,
        )

    assert await _count_submissions(session_maker) == 0
    assert await _count_jobs(session_maker) == 0
