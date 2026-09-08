"""Integration tests for verification-attempt execution."""

import logging
from unittest.mock import AsyncMock
from uuid import uuid4

import httpx
import pytest
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from learn_to_cloud_shared.content_catalog import get_curriculum_catalog
from learn_to_cloud_shared.models import (
    SubmissionValueKind,
    User,
    VerificationAttempt,
    utcnow,
)
from learn_to_cloud_shared.repositories.verification_attempt_repository import (
    VerificationAttemptRepository,
)
from learn_to_cloud_shared.schemas import CriterionResult, TaskResult, ValidationResult
from learn_to_cloud_shared.submission_values import value_kind_for_submission_type
from learn_to_cloud_shared.verification.ci_status import verify_ci_status
from learn_to_cloud_shared.verification.execution import attempt_to_submission_data
from learn_to_cloud_shared.verification.github_errors import (
    GitHubServerError,
    github_error_to_result,
)
from learn_to_cloud_shared.verification.grading_requests import LLMGradingRequest
from learn_to_cloud_shared.verification.repo_files import GitHubRepoFiles
from learn_to_cloud_shared.verification.tasks.base import EvidenceBundle, EvidenceItem
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
from learn_to_cloud_shared.verification_workflow import (
    VerificationRunResult,
)
from tests.fakes.legacy_devops import (
    DEVOPS_IMPLEMENTATION_RUBRIC_TASK,
)
from tests.fakes.repo_ref import InMemoryRepoRef
from tests.fakes.workflow_runs import InMemoryWorkflowRuns

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
    requirement_slug: str | None = None,
) -> VerificationAttempt:
    requirement = (
        get_curriculum_catalog().requirements_by_slug[requirement_slug]
        if requirement_slug is not None
        else _requirement()
    )
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


async def test_capstone_success_persists_commit_and_run_feedback(
    session_maker: async_sessionmaker[AsyncSession],
) -> None:
    attempt = await _create_attempt(
        session_maker, requirement_slug="journal-api-implementation"
    )
    preparation = await prepare_verification_attempt(
        attempt.id, session_maker=session_maker
    )
    sha = "a" * 40
    result = await verify_ci_status(
        "octocat",
        "journal-starter",
        InMemoryWorkflowRuns(
            {
                "id": 789,
                "run_number": 10,
                "head_branch": "main",
                "head_sha": sha,
                "event": "workflow_dispatch",
                "status": "completed",
                "conclusion": "success",
            }
        ),
        InMemoryRepoRef(sha),
    )
    run_result = VerificationRunResult(
        attempt=preparation.attempt, validation_result=result, grading_requests=[]
    )
    await finalize_verification_attempt(
        run_result,
        session_maker=session_maker,
    )
    async with session_maker() as db:
        stored = await db.get(VerificationAttempt, attempt.id)
    assert stored.outcome == "succeeded"
    assert stored.validation_message is None
    assert stored.feedback_json == [result.task_results[0].model_dump()]
    feedback = stored.feedback_json[0]["feedback"]
    assert sha in feedback
    assert "https://github.com/octocat/journal-starter/actions/runs/789" in feedback
    assert not stored.feedback_json[0]["criterion_results"]


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


@pytest.mark.parametrize("passed", [False, True])
async def test_finalize_is_compare_and_set_idempotent(
    session_maker: async_sessionmaker[AsyncSession],
    caplog: pytest.LogCaptureFixture,
    passed: bool,
) -> None:
    attempt = await _create_attempt(session_maker)
    preparation = await prepare_verification_attempt(
        attempt.id, session_maker=session_maker
    )
    run_result = VerificationRunResult(
        attempt=preparation.attempt,
        validation_result=ValidationResult(
            is_valid=passed,
            message="Submission validation details",
            task_results=[
                TaskResult(
                    task_name="Check",
                    passed=passed,
                    feedback="Submission feedback sentinel",
                )
            ],
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
    outcome = "succeeded" if passed else "failed"
    assert first.state.outcome == outcome
    assert first.state.terminal_source == "api_worker"
    assert second.state.outcome == outcome
    assert first.state.completed_at == second.state.completed_at
    records = [
        record
        for record in caplog.records
        if record.message == "verification.attempt.completed"
    ]
    assert len(records) == 1
    assert records[0].__dict__["verification.attempt.id"] == str(attempt.id)
    assert records[0].__dict__["verification.outcome"] == outcome
    async with session_maker() as db:
        stored = await db.get(VerificationAttempt, attempt.id)
        assert stored.submitted_value == attempt.submitted_value
        assert stored.feedback_json[0]["feedback"] == "Submission feedback sentinel"
    telemetry = str([vars(record) for record in records])
    assert attempt.submitted_value not in telemetry
    assert "Submission feedback sentinel" not in telemetry
    assert "Submission validation details" not in telemetry


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


async def test_failed_github_fetch_persists_incomplete_without_completion(
    session_maker: async_sessionmaker[AsyncSession],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    attempt = await _create_attempt(session_maker)
    preparation = await prepare_verification_attempt(
        attempt.id, session_maker=session_maker
    )
    transport = httpx.MockTransport(
        lambda _: httpx.Response(503, text="private upstream details")
    )
    async with httpx.AsyncClient(transport=transport) as client:
        monkeypatch.setattr(
            "learn_to_cloud_shared.verification.repo_files.get_github_client",
            AsyncMock(return_value=client),
        )
        with pytest.raises(GitHubServerError) as raised:
            await GitHubRepoFiles().file("octocat", "repo", "README.md")
    validation = github_error_to_result(
        raised.value, event="llm_rubric_review.repo_file_error"
    )
    run_result = VerificationRunResult(
        attempt=preparation.attempt,
        validation_result=validation,
        grading_requests=[],
    )
    finalized = await finalize_verification_attempt(
        run_result, session_maker=session_maker
    )
    repeated = await finalize_verification_attempt(
        run_result, session_maker=session_maker
    )

    assert finalized.won is True
    assert repeated.won is False
    assert finalized.state.outcome == "server_error"
    assert finalized.state.error_code == "provider_unavailable"
    assert finalized.state.validation_message == (
        "GitHub API error (503). Try again later."
    )
    async with session_maker() as db:
        stored = await db.get(VerificationAttempt, attempt.id)
        completions = await VerificationAttemptRepository(db).list_phase_completions(
            {1: 1}, {attempt.requirement_uuid: 1}
        )
    assert stored is not None
    assert stored.outcome == "server_error"
    assert stored.completed_at is not None
    assert stored.feedback_json is None
    assert (1, attempt.user_id) not in completions


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
            error_code="evidence.total_limit",
        ),
        llm_error_type="llm.provider_unavailable",
    )

    result = await finalize_verification_attempt(
        run_result, session_maker=session_maker
    )

    assert result.state.error_code == "llm.provider_unavailable"
    assert "provider" not in (result.state.validation_message or "").lower()


@pytest.mark.parametrize(
    ("error_code", "completed", "expected_code"),
    [
        ("evidence.required_missing", True, "evidence.required_missing"),
        ("evidence.changed", False, "evidence.changed"),
        ("evidence.file_limit", False, "evidence.file_limit"),
        ("evidence.item_limit", False, "evidence.item_limit"),
        ("evidence.total_limit", False, "evidence.total_limit"),
        ("evidence.selection", False, "evidence.selection"),
        ("evidence.configuration", False, "evidence.configuration"),
        ("authentication", False, "authentication"),
        ("authorization", False, "authorization"),
        ("client_error", False, "client_error"),
        ("network", False, "network"),
        ("provider_unavailable", False, "provider_unavailable"),
        ("rate_limit", False, "rate_limit"),
        ("private-code https://secret.example/path", False, "verification_incomplete"),
    ],
)
async def test_evidence_codes_persist_through_terminal_projections(
    session_maker: async_sessionmaker[AsyncSession],
    caplog: pytest.LogCaptureFixture,
    error_code: str,
    completed: bool,
    expected_code: str,
) -> None:
    attempt = await _create_attempt(session_maker)
    preparation = await prepare_verification_attempt(
        attempt.id, session_maker=session_maker
    )
    run_result = VerificationRunResult(
        attempt=preparation.attempt,
        validation_result=ValidationResult(
            is_valid=False,
            message="The required evidence could not be collected.",
            verification_completed=completed,
            error_code=error_code,
        ),
        grading_requests=[],
        llm_error_type="not-an-allowed-llm-category",
    )
    with caplog.at_level(
        logging.INFO, logger="learn_to_cloud.verification_attempt_executor"
    ):
        result = await finalize_verification_attempt(
            run_result, session_maker=session_maker
        )
        repeated = await finalize_verification_attempt(
            VerificationRunResult(
                attempt=preparation.attempt,
                validation_result=ValidationResult(is_valid=True, message="Stale"),
            ),
            session_maker=session_maker,
        )

    assert result.won is True
    assert repeated.won is False
    assert repeated.state.error_code == expected_code
    assert result.state.error_code == expected_code
    assert result.state.outcome == ("failed" if completed else "server_error")
    async with session_maker() as db:
        repo = VerificationAttemptRepository(db)
        cards = await repo.get_latest_terminal_for_requirements(
            attempt.user_id, [attempt.requirement_uuid]
        )
        history = await repo.list_terminal_history_for_requirements(
            attempt.user_id, [attempt.requirement_uuid], limit=10
        )
        completions = await repo.list_phase_completions(
            {1: 1}, {attempt.requirement_uuid: 1}
        )
    submission = attempt_to_submission_data(cards[0])
    assert cards[0].error_code == history[0].error_code == expected_code
    assert submission.error_code == expected_code
    assert submission.verification_completed is completed
    assert not submission.is_validated
    assert (1, attempt.user_id) not in completions
    assert history[0].feedback_json is None
    records = [
        record
        for record in caplog.records
        if record.message == "verification.attempt.completed"
    ]
    assert len(records) == 1
    assert records[0].__dict__["verification.error.code"] == expected_code
    assert "private-code" not in str(records[0].__dict__)


async def test_incomplete_evidence_does_not_remove_previous_completion(
    session_maker: async_sessionmaker[AsyncSession],
) -> None:
    attempt = await _create_attempt(session_maker)
    preparation = await prepare_verification_attempt(
        attempt.id, session_maker=session_maker
    )
    async with session_maker() as db:
        db.add(
            VerificationAttempt(
                id=uuid4(),
                user_id=attempt.user_id,
                requirement_uuid=attempt.requirement_uuid,
                snapshot_source="reconstructed",
                submission_value_kind=attempt.submission_value_kind,
                submitted_value="previous completion",
                outcome="succeeded",
                completed_at=utcnow(),
            )
        )
        await db.commit()

    await finalize_verification_attempt(
        VerificationRunResult(
            attempt=preparation.attempt,
            validation_result=ValidationResult(
                is_valid=False,
                message="Evidence exceeds the service budget.",
                verification_completed=False,
                error_code="evidence.total_limit",
            ),
        ),
        session_maker=session_maker,
    )

    async with session_maker() as db:
        repo = VerificationAttemptRepository(db)
        completions = await repo.list_phase_completions(
            {1: 1}, {attempt.requirement_uuid: 1}
        )
        succeeded = await repo.count_succeeded_for_requirements(
            attempt.user_id, [attempt.requirement_uuid]
        )
    assert (1, attempt.user_id) in completions
    assert succeeded == 1


async def test_incomplete_finalization_drops_private_evidence_and_stale_prompt(
    session_maker: async_sessionmaker[AsyncSession],
    caplog: pytest.LogCaptureFixture,
) -> None:
    attempt = await _create_attempt(session_maker)
    preparation = await prepare_verification_attempt(
        attempt.id, session_maker=session_maker
    )
    private = "private-evidence-sentinel-https://private.example/repository"
    run_result = VerificationRunResult(
        attempt=preparation.attempt,
        validation_result=ValidationResult(
            is_valid=False,
            message="The verifier could not assemble the required evidence.",
            verification_completed=False,
            error_code="evidence.selection",
        ),
        evidence=[
            EvidenceBundle(
                task_id=DEVOPS_IMPLEMENTATION_RUBRIC_TASK.id,
                source="repo_files",
                items=[
                    EvidenceItem(
                        path="private-evidence-path",
                        content=private,
                        sha256="private-content-hash",
                    )
                ],
                total_bytes=len(private.encode()),
            )
        ],
        grading_requests=[
            LLMGradingRequest(
                task=DEVOPS_IMPLEMENTATION_RUBRIC_TASK,
                message=private,
            )
        ],
    )
    with caplog.at_level(
        logging.INFO, logger="learn_to_cloud.verification_attempt_executor"
    ):
        await finalize_verification_attempt(
            run_result,
            session_maker=session_maker,
        )

    async with session_maker() as db:
        stored = await db.get(VerificationAttempt, attempt.id)
    assert stored is not None
    assert stored.feedback_json is None
    assert stored.error_code == "evidence.selection"
    assert "private-evidence" not in str(vars(stored))
    assert "private-content-hash" not in str(vars(stored))
    assert "private-evidence" not in str([vars(record) for record in caplog.records])
