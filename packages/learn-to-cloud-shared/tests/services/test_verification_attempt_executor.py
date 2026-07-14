"""Integration tests for verification-attempt prepare/finalize/terminalize."""

from __future__ import annotations

from unittest.mock import patch
from uuid import UUID, uuid4

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from learn_to_cloud_shared.content_sync import sync_curriculum_to_db
from learn_to_cloud_shared.content_yaml_loader import clear_cache
from learn_to_cloud_shared.models import (
    CurriculumRequirement,
    Submission,
    SubmissionType,
    VerificationAttempt,
    VerificationAttemptOutcome,
)
from learn_to_cloud_shared.repositories.user_repository import UserRepository
from learn_to_cloud_shared.repositories.verification_attempt_repository import (
    VerificationAttemptRepository,
)
from learn_to_cloud_shared.repositories.verification_job_repository import (
    VerificationJobRepository,
)
from learn_to_cloud_shared.schemas import HandsOnRequirement, ValidationResult
from learn_to_cloud_shared.submission_values import SubmittedValue
from learn_to_cloud_shared.testing.requirement_factories import (
    make_requirement,
    repo_fork_requirement,
)
from learn_to_cloud_shared.verification_attempt_executor import (
    AttemptNotActiveError,
    AttemptNotFoundError,
    AttemptNotRunnableError,
    finalize_verification_attempt,
    prepare_verification_attempt,
    terminalize_verification_attempt,
)
from learn_to_cloud_shared.verification_attempt_snapshot import (
    ATTEMPT_PAYLOAD_VERSION,
    AttemptSnapshotError,
    build_requirement_snapshot,
    compute_snapshot_hash,
)
from learn_to_cloud_shared.verification_job_executor import (
    PreparedVerificationJob,
    VerificationRunResult,
)

pytestmark = pytest.mark.integration

USER_ID = 85001
_VALUE = "https://github.com/attemptexec/repo"


@pytest.fixture()
def session_maker(test_engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(
        bind=test_engine,
        class_=AsyncSession,
        expire_on_commit=False,
        autoflush=False,
    )


@pytest.fixture()
async def user(session_maker: async_sessionmaker[AsyncSession]) -> int:
    async with session_maker() as db:
        await UserRepository(db).upsert(USER_ID, github_username="attemptexec")
        await db.commit()
    return USER_ID


@pytest.fixture()
async def synced_requirement(
    session_maker: async_sessionmaker[AsyncSession],
) -> HandsOnRequirement:
    """Return a requirement whose UUID matches an active curriculum row."""
    clear_cache()
    async with session_maker() as db:
        await sync_curriculum_to_db(db)
        await UserRepository(db).upsert(USER_ID, github_username="attemptexec")
        await db.commit()
        row = (
            await db.execute(
                select(
                    CurriculumRequirement.uuid,
                    CurriculumRequirement.slug,
                    CurriculumRequirement.submission_type,
                )
                .where(CurriculumRequirement.submission_type == "repo_fork")
                .limit(1)
            )
        ).one()
    return make_requirement(
        SubmissionType(row.submission_type),
        slug=row.slug,
        name="Attempt Executor Test",
        description="Test requirement",
    ).model_copy(update={"uuid": row.uuid})


async def _insert_submitted_attempt(
    session_maker: async_sessionmaker[AsyncSession],
    requirement: HandsOnRequirement,
    *,
    attempt_id: UUID | None = None,
    payload_version: int | None = ATTEMPT_PAYLOAD_VERSION,
    snapshot_source: str = "submitted",
    submission_value_kind: str = "github_url",
    legacy_job_id: UUID | None = None,
    tamper_hash: bool = False,
) -> UUID:
    attempt_id = attempt_id or uuid4()
    snapshot = build_requirement_snapshot(requirement)
    snapshot_hash = compute_snapshot_hash(snapshot)
    if tamper_hash:
        snapshot_hash = "deadbeef"
    async with session_maker() as db:
        db.add(
            VerificationAttempt(
                id=attempt_id,
                user_id=USER_ID,
                requirement_uuid=requirement.uuid,
                snapshot_source=snapshot_source,
                payload_version=payload_version,
                requirement_snapshot=snapshot,
                requirement_snapshot_hash=snapshot_hash,
                submission_value_kind=submission_value_kind,
                submitted_value=_VALUE,
                github_username_snapshot="attemptexec",
                legacy_job_id=legacy_job_id,
            )
        )
        await db.commit()
    return attempt_id


def _run_result(
    attempt_id: UUID,
    requirement: HandsOnRequirement,
    *,
    is_valid: bool,
    verification_completed: bool = True,
    message: str = "",
) -> VerificationRunResult:
    job = PreparedVerificationJob(
        id=attempt_id,
        user_id=USER_ID,
        github_username="attemptexec",
        requirement=requirement,
        submitted_value=SubmittedValue.from_kind_and_value("github_url", _VALUE),
    )
    return VerificationRunResult(
        job=job,
        validation_result=ValidationResult(
            is_valid=is_valid,
            message=message,
            verification_completed=verification_completed,
        ),
    )


# --------------------------------------------------------------------------- #
# prepare
# --------------------------------------------------------------------------- #


async def test_prepare_returns_runnable_job(
    session_maker: async_sessionmaker[AsyncSession], user: int
) -> None:
    requirement = repo_fork_requirement(slug="fork", required_repo="owner/repo")
    attempt_id = await _insert_submitted_attempt(session_maker, requirement)
    preparation = await prepare_verification_attempt(
        attempt_id, session_maker=session_maker
    )
    assert preparation.job.id == attempt_id
    assert preparation.job.requirement == requirement
    assert preparation.job.typed_submitted_value.as_text == _VALUE
    async with session_maker() as db:
        status = await VerificationAttemptRepository(db).get_status(attempt_id)
    assert status is not None
    assert status.started_at is not None


async def test_prepare_missing_attempt_raises(
    session_maker: async_sessionmaker[AsyncSession], user: int
) -> None:
    with pytest.raises(AttemptNotFoundError):
        await prepare_verification_attempt(uuid4(), session_maker=session_maker)


async def test_prepare_rejects_terminal_attempt(
    session_maker: async_sessionmaker[AsyncSession], user: int
) -> None:
    requirement = repo_fork_requirement(slug="fork", required_repo="owner/repo")
    attempt_id = await _insert_submitted_attempt(session_maker, requirement)
    async with session_maker() as db:
        await VerificationAttemptRepository(db).finalize(
            attempt_id,
            outcome=VerificationAttemptOutcome.SUCCEEDED,
            error_code="verification_succeeded",
            validation_message=None,
            terminal_source="orchestrator",
            feedback_json=None,
        )
        await db.commit()
    with pytest.raises(AttemptNotActiveError):
        await prepare_verification_attempt(attempt_id, session_maker=session_maker)


async def test_prepare_rechecks_terminal_state_after_start_cas_loss(
    session_maker: async_sessionmaker[AsyncSession], user: int
) -> None:
    requirement = repo_fork_requirement(slug="fork", required_repo="owner/repo")
    attempt_id = await _insert_submitted_attempt(session_maker, requirement)

    async def terminalize_before_start_mark(
        _repo: VerificationAttemptRepository,
        claimed_attempt_id: UUID,
        *,
        started_at=None,
    ) -> bool:
        async with session_maker() as competing_db:
            await VerificationAttemptRepository(competing_db).finalize(
                claimed_attempt_id,
                outcome=VerificationAttemptOutcome.SERVER_ERROR,
                error_code="server_error",
                validation_message="reconciled",
                terminal_source="reconciler",
                feedback_json=None,
            )
            await competing_db.commit()
        return False

    with (
        patch.object(
            VerificationAttemptRepository,
            "mark_started",
            new=terminalize_before_start_mark,
        ),
        pytest.raises(AttemptNotActiveError),
    ):
        await prepare_verification_attempt(attempt_id, session_maker=session_maker)


async def test_prepare_is_idempotent_after_started_at_is_set(
    session_maker: async_sessionmaker[AsyncSession], user: int
) -> None:
    requirement = repo_fork_requirement(slug="fork", required_repo="owner/repo")
    attempt_id = await _insert_submitted_attempt(session_maker, requirement)
    first = await prepare_verification_attempt(attempt_id, session_maker=session_maker)
    second = await prepare_verification_attempt(attempt_id, session_maker=session_maker)
    assert first == second


async def test_prepare_rejects_reconstructed_source(
    session_maker: async_sessionmaker[AsyncSession], user: int
) -> None:
    requirement = repo_fork_requirement(slug="fork", required_repo="owner/repo")
    attempt_id = await _insert_submitted_attempt(
        session_maker, requirement, snapshot_source="reconstructed"
    )
    with pytest.raises(AttemptNotRunnableError):
        await prepare_verification_attempt(attempt_id, session_maker=session_maker)


async def test_prepare_rejects_unsupported_payload_version(
    session_maker: async_sessionmaker[AsyncSession], user: int
) -> None:
    requirement = repo_fork_requirement(slug="fork", required_repo="owner/repo")
    attempt_id = await _insert_submitted_attempt(
        session_maker, requirement, payload_version=999
    )
    with pytest.raises(AttemptSnapshotError, match="payload_version"):
        await prepare_verification_attempt(attempt_id, session_maker=session_maker)


async def test_prepare_rejects_hash_mismatch(
    session_maker: async_sessionmaker[AsyncSession], user: int
) -> None:
    requirement = repo_fork_requirement(slug="fork", required_repo="owner/repo")
    attempt_id = await _insert_submitted_attempt(
        session_maker, requirement, tamper_hash=True
    )
    with pytest.raises(AttemptSnapshotError, match="hash"):
        await prepare_verification_attempt(attempt_id, session_maker=session_maker)


async def test_prepare_rejects_value_kind_mismatch(
    session_maker: async_sessionmaker[AsyncSession], user: int
) -> None:
    requirement = repo_fork_requirement(slug="fork", required_repo="owner/repo")
    attempt_id = await _insert_submitted_attempt(
        session_maker, requirement, submission_value_kind="token"
    )
    with pytest.raises(AttemptSnapshotError, match="submission_value_kind"):
        await prepare_verification_attempt(attempt_id, session_maker=session_maker)


# --------------------------------------------------------------------------- #
# finalize (no legacy mirror)
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    ("is_valid", "verification_completed", "expected"),
    [
        (True, True, "succeeded"),
        (False, True, "failed"),
        (False, False, "server_error"),
    ],
)
async def test_finalize_maps_outcomes(
    session_maker: async_sessionmaker[AsyncSession],
    user: int,
    is_valid: bool,
    verification_completed: bool,
    expected: str,
) -> None:
    requirement = repo_fork_requirement(slug="fork", required_repo="owner/repo")
    attempt_id = await _insert_submitted_attempt(session_maker, requirement)
    state = await finalize_verification_attempt(
        _run_result(
            attempt_id,
            requirement,
            is_valid=is_valid,
            verification_completed=verification_completed,
            message="nope" if not is_valid else "",
        ),
        session_maker=session_maker,
    )
    assert state.outcome == expected
    async with session_maker() as db:
        stored = await VerificationAttemptRepository(db).get_status(attempt_id)
    assert stored is not None
    assert stored.outcome == expected


async def test_finalize_replay_does_not_overwrite(
    session_maker: async_sessionmaker[AsyncSession], user: int
) -> None:
    requirement = repo_fork_requirement(slug="fork", required_repo="owner/repo")
    attempt_id = await _insert_submitted_attempt(session_maker, requirement)
    await finalize_verification_attempt(
        _run_result(attempt_id, requirement, is_valid=True),
        session_maker=session_maker,
    )
    # A replay carrying a different (failed) result must not clobber success.
    state = await finalize_verification_attempt(
        _run_result(attempt_id, requirement, is_valid=False, message="late failure"),
        session_maker=session_maker,
    )
    assert state.outcome == "succeeded"


# --------------------------------------------------------------------------- #
# legacy mirror
# --------------------------------------------------------------------------- #


async def _create_legacy_job(
    session_maker: async_sessionmaker[AsyncSession],
    requirement: HandsOnRequirement,
) -> UUID:
    async with session_maker() as db:
        job = await VerificationJobRepository(db).create(
            user_id=USER_ID,
            requirement_uuid=requirement.uuid,
            submitted_value=SubmittedValue.from_kind_and_value("github_url", _VALUE),
            extracted_username="attemptexec",
        )
        await db.commit()
        return job.id


async def _count_submissions(
    session_maker: async_sessionmaker[AsyncSession],
) -> int:
    async with session_maker() as db:
        return (
            await db.execute(select(func.count()).select_from(Submission))
        ).scalar_one()


async def test_finalize_mirrors_legacy_submission(
    session_maker: async_sessionmaker[AsyncSession],
    synced_requirement: HandsOnRequirement,
) -> None:
    job_id = await _create_legacy_job(session_maker, synced_requirement)
    attempt_id = await _insert_submitted_attempt(
        session_maker, synced_requirement, attempt_id=job_id, legacy_job_id=job_id
    )
    await finalize_verification_attempt(
        _run_result(attempt_id, synced_requirement, is_valid=True),
        session_maker=session_maker,
    )
    async with session_maker() as db:
        job = await VerificationJobRepository(db).get_by_id(job_id)
        assert job is not None
        assert job.result_submission_id is not None
        submission = await db.get(Submission, job.result_submission_id)
    assert submission is not None
    assert submission.is_validated is True
    assert submission.extracted_username == "attemptexec"


async def test_legacy_mirror_is_idempotent(
    session_maker: async_sessionmaker[AsyncSession],
    synced_requirement: HandsOnRequirement,
) -> None:
    job_id = await _create_legacy_job(session_maker, synced_requirement)
    attempt_id = await _insert_submitted_attempt(
        session_maker, synced_requirement, attempt_id=job_id, legacy_job_id=job_id
    )
    before = await _count_submissions(session_maker)
    await finalize_verification_attempt(
        _run_result(attempt_id, synced_requirement, is_valid=False, message="x"),
        session_maker=session_maker,
    )
    after_first = await _count_submissions(session_maker)
    # Re-run finalize (Durable retry): no duplicate legacy submission.
    await finalize_verification_attempt(
        _run_result(attempt_id, synced_requirement, is_valid=False, message="x"),
        session_maker=session_maker,
    )
    after_second = await _count_submissions(session_maker)
    assert after_first == before + 1
    assert after_second == after_first


# --------------------------------------------------------------------------- #
# terminalize (+ reconciler mirror)
# --------------------------------------------------------------------------- #


async def test_terminalize_server_error(
    session_maker: async_sessionmaker[AsyncSession], user: int
) -> None:
    requirement = repo_fork_requirement(slug="fork", required_repo="owner/repo")
    attempt_id = await _insert_submitted_attempt(session_maker, requirement)
    state = await terminalize_verification_attempt(
        attempt_id,
        outcome=VerificationAttemptOutcome.SERVER_ERROR,
        error_code="server_error",
        validation_message="Verification could not be completed.",
        terminal_source="orchestrator_exception",
        session_maker=session_maker,
    )
    assert state.outcome == "server_error"
    assert state.terminal_source == "orchestrator_exception"


async def test_terminalize_cancelled_mirrors_legacy(
    session_maker: async_sessionmaker[AsyncSession],
    synced_requirement: HandsOnRequirement,
) -> None:
    job_id = await _create_legacy_job(session_maker, synced_requirement)
    attempt_id = await _insert_submitted_attempt(
        session_maker, synced_requirement, attempt_id=job_id, legacy_job_id=job_id
    )
    state = await terminalize_verification_attempt(
        attempt_id,
        outcome=VerificationAttemptOutcome.CANCELLED,
        error_code="cancelled",
        validation_message="Verification was cancelled.",
        terminal_source="reconciler",
        session_maker=session_maker,
    )
    assert state.outcome == "cancelled"
    async with session_maker() as db:
        job = await VerificationJobRepository(db).get_by_id(job_id)
        assert job is not None and job.result_submission_id is not None
        submission = await db.get(Submission, job.result_submission_id)
    assert submission is not None
    assert submission.is_validated is False
    assert submission.verification_completed is False


async def test_mirror_skips_when_legacy_job_already_linked(
    session_maker: async_sessionmaker[AsyncSession],
    synced_requirement: HandsOnRequirement,
) -> None:
    job_id = await _create_legacy_job(session_maker, synced_requirement)
    # The legacy execution path linked its own submission first.
    async with session_maker() as db:
        from learn_to_cloud_shared.repositories.submission_repository import (
            SubmissionRepository,
        )

        submission = await SubmissionRepository(db).create(
            user_id=USER_ID,
            requirement_uuid=synced_requirement.uuid,
            submitted_value=SubmittedValue.from_kind_and_value("github_url", _VALUE),
            extracted_username="attemptexec",
            is_validated=True,
            verification_completed=True,
        )
        await VerificationJobRepository(db).link_submission(job_id, submission.id)
        await db.commit()
        linked_submission_id = submission.id

    attempt_id = await _insert_submitted_attempt(
        session_maker, synced_requirement, attempt_id=job_id, legacy_job_id=job_id
    )
    before = await _count_submissions(session_maker)
    await terminalize_verification_attempt(
        attempt_id,
        outcome=VerificationAttemptOutcome.SERVER_ERROR,
        error_code="server_error",
        validation_message="Verification could not be completed.",
        terminal_source="reconciler",
        session_maker=session_maker,
    )
    after = await _count_submissions(session_maker)
    assert after == before
    async with session_maker() as db:
        job = await VerificationJobRepository(db).get_by_id(job_id)
    assert job is not None
    assert job.result_submission_id == linked_submission_id
