"""Integration tests for verification-attempt execution."""

from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from learn_to_cloud_shared.content_catalog import get_curriculum_catalog
from learn_to_cloud_shared.models import SubmissionValueKind, User, VerificationAttempt
from learn_to_cloud_shared.repositories.verification_attempt_repository import (
    VerificationAttemptRepository,
)
from learn_to_cloud_shared.schemas import ValidationResult
from learn_to_cloud_shared.submission_values import value_kind_for_submission_type
from learn_to_cloud_shared.verification_attempt_executor import (
    AttemptNotRunnableError,
    finalize_verification_attempt,
    prepare_verification_attempt,
    terminalize_verification_attempt,
)
from learn_to_cloud_shared.verification_attempt_snapshot import (
    ATTEMPT_PAYLOAD_VERSION,
    build_requirement_snapshot,
    compute_snapshot_hash,
)
from learn_to_cloud_shared.verification_workflow import VerificationRunResult

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]


@pytest.fixture()
def session_maker(test_engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(
        bind=test_engine,
        class_=AsyncSession,
        expire_on_commit=False,
        autoflush=False,
    )


def _requirement():
    return next(iter(get_curriculum_catalog().requirements_by_uuid.values()))


async def _create_attempt(
    session_maker: async_sessionmaker[AsyncSession],
    *,
    reconstructed: bool = False,
) -> VerificationAttempt:
    requirement = _requirement()
    value_kind = value_kind_for_submission_type(requirement.submission_type)
    submitted_value = {
        SubmissionValueKind.GITHUB_URL: "https://github.com/octocat/repo",
        SubmissionValueKind.TOKEN: "token-value",
        SubmissionValueKind.DEPLOYED_URL: "https://example.com",
        SubmissionValueKind.TEXT: "verification input",
    }[value_kind]
    snapshot = build_requirement_snapshot(requirement)
    attempt = VerificationAttempt(
        id=uuid4(),
        user_id=82001,
        requirement_uuid=requirement.uuid,
        artifact_schema_version=None if reconstructed else 1,
        curriculum_version=None if reconstructed else 1,
        content_hash=None if reconstructed else "content",
        requirement_snapshot=None if reconstructed else snapshot,
        requirement_snapshot_hash=(
            None if reconstructed else compute_snapshot_hash(snapshot)
        ),
        snapshot_source="reconstructed" if reconstructed else "submitted",
        payload_version=None if reconstructed else ATTEMPT_PAYLOAD_VERSION,
        github_username_snapshot="octocat",
        submission_value_kind=value_kind.value,
        submitted_value=submitted_value,
    )
    async with session_maker() as db:
        if await db.get(User, 82001) is None:
            db.add(User(id=82001, github_username="octocat"))
        db.add(attempt)
        await db.commit()
    return attempt


async def test_prepare_loads_snapshot_and_marks_attempt_started(
    session_maker: async_sessionmaker[AsyncSession],
) -> None:
    attempt = await _create_attempt(session_maker)

    preparation = await prepare_verification_attempt(
        attempt.id, session_maker=session_maker
    )

    assert preparation.attempt.id == attempt.id
    assert preparation.attempt.requirement.uuid == attempt.requirement_uuid
    async with session_maker() as db:
        status = await VerificationAttemptRepository(db).get_status(attempt.id)
    assert status is not None
    assert status.started_at is not None


async def test_prepare_rejects_reconstructed_attempt(
    session_maker: async_sessionmaker[AsyncSession],
) -> None:
    attempt = await _create_attempt(session_maker, reconstructed=True)

    with pytest.raises(AttemptNotRunnableError):
        await prepare_verification_attempt(attempt.id, session_maker=session_maker)


async def test_finalize_is_compare_and_set_idempotent(
    session_maker: async_sessionmaker[AsyncSession],
) -> None:
    attempt = await _create_attempt(session_maker)
    preparation = await prepare_verification_attempt(
        attempt.id, session_maker=session_maker
    )
    run_result = VerificationRunResult(
        attempt=preparation.attempt,
        validation_result=ValidationResult(
            is_valid=True,
            message="Verified.",
        ),
    )

    first = await finalize_verification_attempt(run_result, session_maker=session_maker)
    second = await finalize_verification_attempt(
        run_result, session_maker=session_maker
    )

    assert first.outcome == "succeeded"
    assert second.outcome == "succeeded"
    assert first.completed_at == second.completed_at


async def test_terminalize_records_cancelled_outcome(
    session_maker: async_sessionmaker[AsyncSession],
) -> None:
    attempt = await _create_attempt(session_maker)

    state = await terminalize_verification_attempt(
        attempt.id,
        outcome="cancelled",
        error_code="cancelled",
        validation_message="Verification was cancelled.",
        terminal_source="test",
        session_maker=session_maker,
    )

    assert state.outcome == "cancelled"
    assert state.error_code == "cancelled"
