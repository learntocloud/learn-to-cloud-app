"""Integration tests for verification-attempt execution."""

import logging
from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from learn_to_cloud_shared.content_catalog import get_curriculum_catalog
from learn_to_cloud_shared.models import SubmissionValueKind, User, VerificationAttempt
from learn_to_cloud_shared.repositories.verification_attempt_repository import (
    VerificationAttemptRepository,
)
from learn_to_cloud_shared.schemas import CriterionResult, TaskResult, ValidationResult
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
    caplog: pytest.LogCaptureFixture,
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

    with caplog.at_level(
        logging.INFO,
        logger="learn_to_cloud.verification_attempt_executor",
    ):
        first = await finalize_verification_attempt(
            run_result, session_maker=session_maker
        )
        second = await finalize_verification_attempt(
            run_result, session_maker=session_maker
        )

    assert first.won is True
    assert second.won is False
    assert first.state.outcome == "succeeded"
    assert second.state.outcome == "succeeded"
    assert first.state.completed_at == second.state.completed_at
    records = [
        record
        for record in caplog.records
        if record.message == "verification.attempt.completed"
    ]
    assert len(records) == 1
    assert records[0].__dict__["verification.attempt.id"] == str(attempt.id)
    assert records[0].__dict__["verification.outcome"] == "succeeded"


async def test_finalize_persists_structured_criterion_feedback(
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
            task_results=[
                TaskResult(
                    task_name="Journal API review",
                    passed=True,
                    feedback="The implementation passed.",
                    criterion_results=[
                        CriterionResult(
                            criterion_id="application-logging",
                            label="Application logging",
                            status="met",
                            explanation="Logging is configured.",
                            evidence_refs=["api/main.py"],
                        )
                    ],
                )
            ],
        ),
    )

    await finalize_verification_attempt(run_result, session_maker=session_maker)

    async with session_maker() as db:
        stored = await db.get(VerificationAttempt, attempt.id)
    assert stored is not None
    assert stored.feedback_json is not None
    criterion = stored.feedback_json[0]["criterion_results"][0]
    assert criterion["criterion_id"] == "application-logging"
    assert criterion["evidence_refs"] == ["api/main.py"]


async def test_terminalize_records_cancelled_outcome(
    session_maker: async_sessionmaker[AsyncSession],
) -> None:
    attempt = await _create_attempt(session_maker)

    result = await terminalize_verification_attempt(
        attempt.id,
        outcome="cancelled",
        error_code="cancelled",
        validation_message="Verification was cancelled.",
        terminal_source="test",
        session_maker=session_maker,
    )

    assert result.won is True
    assert result.state.outcome == "cancelled"


async def test_finalize_persists_only_safe_llm_error_category(
    session_maker: async_sessionmaker[AsyncSession],
) -> None:
    attempt = await _create_attempt(session_maker)
    preparation = await prepare_verification_attempt(
        attempt.id, session_maker=session_maker
    )
    run_result = VerificationRunResult(
        attempt=preparation.attempt,
        validation_result=ValidationResult(
            is_valid=False,
            message=(
                "Automated grading is temporarily unavailable. "
                "Please submit again later."
            ),
            verification_completed=False,
        ),
        llm_error_type="llm.provider_unavailable",
    )

    result = await finalize_verification_attempt(
        run_result, session_maker=session_maker
    )

    assert result.state.error_code == "llm.provider_unavailable"
    assert "provider" not in (result.state.validation_message or "").lower()
