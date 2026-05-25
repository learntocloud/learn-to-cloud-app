"""Integration tests for persisted verification job execution."""

from unittest.mock import AsyncMock, patch
from uuid import UUID

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from learn_to_cloud_shared.content_sync import sync_curriculum_to_db
from learn_to_cloud_shared.content_yaml_loader import clear_cache
from learn_to_cloud_shared.models import (
    CurriculumRequirement,
    Submission,
    SubmissionType,
    SubmissionValueKind,
    VerificationJob,
)
from learn_to_cloud_shared.repositories.user_repository import UserRepository
from learn_to_cloud_shared.repositories.verification_job_repository import (
    VerificationJobRepository,
)
from learn_to_cloud_shared.schemas import HandsOnRequirement, ValidationResult
from learn_to_cloud_shared.submission_values import SubmittedValue
from learn_to_cloud_shared.verification.execution import MAX_VALIDATION_MESSAGE_LENGTH
from learn_to_cloud_shared.verification_job_executor import (
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


def _github_value(value: str) -> SubmittedValue:
    return SubmittedValue(kind=SubmissionValueKind.GITHUB_URL, github_url=value)


@pytest.fixture()
def session_maker(test_engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(
        bind=test_engine,
        class_=AsyncSession,
        expire_on_commit=False,
        autoflush=False,
    )


@pytest.fixture()
async def synced_requirement(
    session_maker: async_sessionmaker[AsyncSession],
) -> HandsOnRequirement:
    """Sync the real curriculum and return a HandsOnRequirement whose
    UUID + id match an active row in the ``requirements`` table.

    Phase D.2 added an FK on ``submissions.requirement_uuid``; tests
    persisting submissions need the referenced requirement to exist,
    and ``get_requirement_by_slug`` only returns active rows so the test
    requirement must be alive in the curriculum.
    """
    from learn_to_cloud_shared.testing.requirement_factories import (
        make_requirement,
    )

    clear_cache()
    async with session_maker() as db:
        await sync_curriculum_to_db(db)
        await UserRepository(db).upsert(USER_ID, github_username="executoruser")
        await db.commit()
        row = (
            await db.execute(
                select(
                    CurriculumRequirement.uuid,
                    CurriculumRequirement.slug,
                    CurriculumRequirement.submission_type,
                )
                .where(CurriculumRequirement.submission_type == "journal_api_verifier")
                .limit(1)
            )
        ).one()

    return make_requirement(
        SubmissionType(row.submission_type),
        slug=row.slug,
        name="Verification Executor Test",
        description="Test requirement",
    ).model_copy(update={"uuid": row.uuid})


async def _create_job(
    session_maker: async_sessionmaker[AsyncSession],
    requirement: HandsOnRequirement,
) -> UUID:
    async with session_maker() as db:
        job = await VerificationJobRepository(db).create(
            user_id=USER_ID,
            requirement_uuid=requirement.uuid,
            submitted_value=_github_value("https://github.com/executoruser/repo"),
        )
        await db.commit()
        return job.id


def _prepared(job_id: UUID, requirement: HandsOnRequirement) -> PreparedVerificationJob:
    """Build the PreparedVerificationJob the orchestration would carry."""
    return PreparedVerificationJob(
        id=job_id,
        user_id=USER_ID,
        github_username="executoruser",
        requirement=requirement,
        submitted_value=_github_value("https://github.com/executoruser/repo"),
    )


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
    synced_requirement: HandsOnRequirement,
):
    job_id = await _create_job(session_maker, synced_requirement)
    validation = AsyncMock(
        return_value=ValidationResult(is_valid=True, message="Verified")
    )
    preparation = await prepare_verification_job(
        job_id,
        session_maker=session_maker,
        prepared_input=_prepared(job_id, synced_requirement),
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
    synced_requirement: HandsOnRequirement,
):
    job_id = await _create_job(session_maker, synced_requirement)
    validation = AsyncMock(
        return_value=ValidationResult(is_valid=True, message="Verified")
    )

    with (
        patch(
            "learn_to_cloud_shared.verification_job_executor.validate_submission",
            validation,
        ),
    ):
        result = await execute_verification_job(
            job_id,
            session_maker=session_maker,
            prepared_input=_prepared(job_id, synced_requirement),
        )

    assert result.status == "succeeded"
    assert result.submission_id is not None
    assert result.is_valid is True
    assert result.verification_completed is True
    payload = result.to_payload()
    assert payload["status"] == "succeeded"
    assert payload["code"] == VERIFICATION_SUCCEEDED_CODE
    assert payload["requirement_slug"] == synced_requirement.slug
    assert payload["requirement_name"] == "Verification Executor Test"
    assert payload["submission_type"] == SubmissionType.JOURNAL_API_VERIFIER.value
    assert payload["message"] == "Verification succeeded."
    # On success there is no validation message; ``detail`` is None.
    assert payload["detail"] is None

    assert await _get_job_link(session_maker, job_id) == result.submission_id
    submission = await _get_submission(session_maker, result.submission_id)
    assert submission.is_validated is True


async def test_execute_verification_job_marks_user_validation_failure(
    session_maker: async_sessionmaker[AsyncSession],
    synced_requirement: HandsOnRequirement,
):
    job_id = await _create_job(session_maker, synced_requirement)
    validation = AsyncMock(
        return_value=ValidationResult(
            is_valid=False,
            message="GitHub username does not match",
            verification_completed=True,
        )
    )

    with (
        patch(
            "learn_to_cloud_shared.verification_job_executor.validate_submission",
            validation,
        ),
    ):
        result = await execute_verification_job(
            job_id,
            session_maker=session_maker,
            prepared_input=_prepared(job_id, synced_requirement),
        )

    assert result.status == "failed"
    assert result.code == VALIDATION_FAILED_ERROR_CODE
    assert result.is_valid is False
    assert result.verification_completed is True
    assert result.detail == "GitHub username does not match"

    assert await _get_job_link(session_maker, job_id) == result.submission_id


async def test_execute_verification_job_marks_server_error(
    session_maker: async_sessionmaker[AsyncSession],
    synced_requirement: HandsOnRequirement,
):
    """A validator returning ``verification_completed=False`` records a
    server-error result. The Submission row exists and is linked but
    is_validated=False / verification_completed=False."""
    job_id = await _create_job(session_maker, synced_requirement)
    validation = AsyncMock(
        return_value=ValidationResult(
            is_valid=False,
            message="GitHub API unavailable",
            verification_completed=False,
        )
    )

    with (
        patch(
            "learn_to_cloud_shared.verification_job_executor.validate_submission",
            validation,
        ),
    ):
        result = await execute_verification_job(
            job_id,
            session_maker=session_maker,
            prepared_input=_prepared(job_id, synced_requirement),
        )

    assert result.status == "server_error"
    assert result.code == VERIFICATION_INCOMPLETE_ERROR_CODE
    assert result.verification_completed is False
    assert result.detail == "GitHub API unavailable"

    submission = await _get_submission(session_maker, result.submission_id)
    assert submission.is_validated is False
    assert submission.verification_completed is False


async def test_execute_verification_job_truncates_persisted_error_messages(
    session_maker: async_sessionmaker[AsyncSession],
    synced_requirement: HandsOnRequirement,
):
    """Validation messages over the persisted limit are truncated for
    storage; the ``detail`` in the activity result follows the same
    rule."""
    job_id = await _create_job(session_maker, synced_requirement)
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
            "learn_to_cloud_shared.verification_job_executor.validate_submission",
            validation,
        ),
    ):
        result = await execute_verification_job(
            job_id,
            session_maker=session_maker,
            prepared_input=_prepared(job_id, synced_requirement),
        )

    assert result.status == "failed"
    assert result.detail is not None
    assert len(result.detail) <= MAX_VALIDATION_MESSAGE_LENGTH


async def test_execute_verification_job_rejects_payload_mismatch(
    session_maker: async_sessionmaker[AsyncSession],
    synced_requirement: HandsOnRequirement,
):
    """A forged payload (whose ``requirement.uuid`` or ``user_id`` does
    not match the persisted ``verification_jobs`` row) is rejected via
    ``VerificationJobNotFoundError`` so the orchestration cannot run
    validation against an arbitrary user/requirement pair.

    Replaces the old soft-deleted-requirement test: after #467 the
    requirement definition travels with the orchestration, so the
    missing-requirement scenario no longer applies. The new failure
    mode the validation guards against is payload tampering.
    """
    job_id = await _create_job(session_maker, synced_requirement)
    forged = _prepared(job_id, synced_requirement)
    # Forge by replacing user_id; requirement.uuid + submitted_value
    # still match the DB row, but the start-time identity does not.
    forged = PreparedVerificationJob(
        id=forged.id,
        user_id=forged.user_id + 1,
        github_username=forged.github_username,
        requirement=forged.requirement,
        submitted_value=forged.submitted_value,
    )

    with pytest.raises(VerificationJobNotFoundError, match="does not match"):
        await execute_verification_job(
            job_id, session_maker=session_maker, prepared_input=forged
        )


async def test_execute_verification_job_is_idempotent_for_terminal_jobs(
    session_maker: async_sessionmaker[AsyncSession],
    synced_requirement: HandsOnRequirement,
):
    """The replay short-circuit fires when the job already has a linked
    Submission; the result is reconstructed from that Submission rather
    than running the validator again."""
    job_id = await _create_job(session_maker, synced_requirement)
    validation = AsyncMock(
        return_value=ValidationResult(is_valid=True, message="Verified")
    )

    with (
        patch(
            "learn_to_cloud_shared.verification_job_executor.validate_submission",
            validation,
        ),
    ):
        first = await execute_verification_job(
            job_id,
            session_maker=session_maker,
            prepared_input=_prepared(job_id, synced_requirement),
        )
        # Reset the validator so the retry would clearly be observable
        # if the short-circuit weren't in place.
        validation.reset_mock()
        second = await execute_verification_job(
            job_id,
            session_maker=session_maker,
            prepared_input=_prepared(job_id, synced_requirement),
        )

    assert first.status == "succeeded"
    assert second.status == "succeeded"
    assert second.submission_id == first.submission_id
    assert await _count_submissions(session_maker) == 1
    validation.assert_not_awaited()


async def test_persist_is_idempotent_via_result_submission_id_guard(
    session_maker: async_sessionmaker[AsyncSession],
    synced_requirement: HandsOnRequirement,
):
    """A second ``persist_verification_result`` call after the first one
    linked a Submission must short-circuit on the result_submission_id
    guard, not write a duplicate row."""
    job_id = await _create_job(session_maker, synced_requirement)

    prepared = PreparedVerificationJob(
        id=job_id,
        user_id=USER_ID,
        github_username="executoruser",
        requirement=synced_requirement,
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
    synced_requirement: HandsOnRequirement,
):
    """If the poller's ``delete_active`` won the race the persist
    activity raises ``VerificationJobNotFoundError`` rather than
    creating an orphan Submission."""
    job_id = await _create_job(session_maker, synced_requirement)

    # Simulate the poller having deleted the row mid-flight.
    async with session_maker() as db:
        deleted = await VerificationJobRepository(db).delete_active(job_id)
        await db.commit()
        assert deleted is True

    prepared = PreparedVerificationJob(
        id=job_id,
        user_id=USER_ID,
        github_username="executoruser",
        requirement=synced_requirement,
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
