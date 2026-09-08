"""Background execution uses bounded attempts, not whole-attempt retries."""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from learn_to_cloud_shared.core.config import VerificationWorkerConfig
from learn_to_cloud_shared.repositories.verification_attempt_repository import (
    AttemptAlreadyGoneError,
)
from sqlalchemy.exc import OperationalError

from learn_to_cloud.services import verification_worker as worker

pytestmark = pytest.mark.unit


@pytest.fixture
def dependencies():
    db = AsyncMock()
    sessions = MagicMock()
    sessions.return_value.__aenter__.return_value = db
    with (
        patch.object(
            worker, "execute_verification_attempt", new_callable=AsyncMock
        ) as run,
        patch.object(
            worker, "terminalize_verification_attempt", new_callable=AsyncMock
        ) as fail,
        patch.object(
            worker, "expire_verification_attempts", new_callable=AsyncMock
        ) as expire,
        patch.object(worker, "VerificationAttemptRepository") as repository,
    ):
        repository.return_value.claim_pending = AsyncMock(return_value=None)
        yield sessions, db, run, fail, expire, repository.return_value


async def test_executes_claimed_attempt_once(dependencies):
    sessions, _, run, fail, *_ = dependencies
    attempt_id = uuid4()
    await worker._execute(attempt_id, sessions, VerificationWorkerConfig())
    run.assert_awaited_once_with(attempt_id, session_maker=sessions)
    fail.assert_not_awaited()


@pytest.mark.parametrize(
    ("error", "code"),
    [
        (TimeoutError(), "verification_timeout"),
        (RuntimeError("private evidence"), "verification_error"),
    ],
)
async def test_failure_is_terminal_without_retry(dependencies, error, code, caplog):
    sessions, _, run, fail, *_ = dependencies
    run.side_effect = error
    attempt_id = uuid4()
    await worker._execute(attempt_id, sessions, VerificationWorkerConfig())
    run.assert_awaited_once()
    assert fail.await_args.kwargs["error_code"] == code
    assert fail.await_args.kwargs["outcome"] == "server_error"
    assert "private evidence" not in caplog.text


async def test_shutdown_terminalizes_active_attempt_and_propagates_cancellation(
    dependencies,
):
    sessions, _, run, fail, *_ = dependencies
    entered = asyncio.Event()
    attempt_id = uuid4()

    async def wait(claimed_attempt_id, *, session_maker):
        entered.set()
        assert claimed_attempt_id == attempt_id
        assert session_maker is sessions
        await asyncio.Event().wait()

    run.side_effect = wait
    task = asyncio.create_task(
        worker._execute(attempt_id, sessions, VerificationWorkerConfig())
    )
    await asyncio.wait_for(entered.wait(), timeout=5)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    run.assert_awaited_once_with(attempt_id, session_maker=sessions)
    assert fail.await_args.kwargs["error_code"] == "verification_interrupted"


async def test_execution_deadline_cancels_work(dependencies):
    sessions, _, run, fail, *_ = dependencies
    cancelled = asyncio.Event()
    attempt_id = uuid4()

    async def wait(claimed_attempt_id, *, session_maker):
        assert claimed_attempt_id == attempt_id
        assert session_maker is sessions
        try:
            await asyncio.Event().wait()
        finally:
            cancelled.set()

    run.side_effect = wait
    await worker._execute(
        attempt_id, sessions, VerificationWorkerConfig(execution_timeout_seconds=1)
    )
    run.assert_awaited_once_with(attempt_id, session_maker=sessions)
    assert cancelled.is_set()
    assert fail.await_args.kwargs["error_code"] == "verification_timeout"


async def test_failed_finalization_is_visible_and_not_retried(dependencies, caplog):
    sessions, _, _, fail, *_ = dependencies
    fail.side_effect = OperationalError("private SQL", {}, RuntimeError("private"))
    await worker._fail_attempt(
        uuid4(), "verification_error", sessions, VerificationWorkerConfig()
    )
    fail.assert_awaited_once()
    assert "verification.attempt.finalize_failed" in caplog.text
    assert "private" not in caplog.text


async def test_claim_is_committed_before_execution(dependencies):
    sessions, db, _, _, expire, repo = dependencies
    attempt_id = uuid4()
    config = VerificationWorkerConfig()
    repo.claim_pending.return_value = attempt_id

    def execute(claimed_attempt_id, session_maker, worker_config):
        assert claimed_attempt_id == attempt_id
        assert session_maker is sessions
        assert worker_config is config
        db.commit.assert_awaited_once()
        raise asyncio.CancelledError

    with patch.object(worker, "_execute", side_effect=execute) as execute_mock:
        with pytest.raises(asyncio.CancelledError):
            await worker.run_verification_worker(sessions, config)
    execute_mock.assert_awaited_once_with(attempt_id, sessions, config)
    expire.assert_awaited_once()


async def test_empty_queue_sleeps(dependencies):
    sessions, *_ = dependencies
    with patch.object(
        worker.asyncio, "sleep", side_effect=asyncio.CancelledError
    ) as sleep:
        with pytest.raises(asyncio.CancelledError):
            await worker.run_verification_worker(sessions, VerificationWorkerConfig())
    sleep.assert_awaited_once_with(5)


async def test_database_error_backs_off_without_execution(dependencies, caplog):
    sessions, _, run, _, expire, _ = dependencies
    expire.side_effect = OperationalError("private", {}, RuntimeError())
    with patch.object(worker.asyncio, "sleep", side_effect=asyncio.CancelledError):
        with pytest.raises(asyncio.CancelledError):
            await worker.run_verification_worker(sessions, VerificationWorkerConfig())
    run.assert_not_awaited()
    assert "verification.worker.database_unavailable" in caplog.text
    assert "private" not in caplog.text


async def test_unexpected_worker_failure_propagates(dependencies, caplog):
    sessions, _, _, _, expire, _ = dependencies
    expire.side_effect = RuntimeError("private")
    with pytest.raises(RuntimeError):
        await worker.run_verification_worker(sessions, VerificationWorkerConfig())
    assert "verification.worker.failed" in caplog.text
    assert "private" not in caplog.text


async def test_account_deletion_does_not_stop_worker(dependencies, caplog):
    sessions, _, run, fail, *_ = dependencies
    attempt_id = uuid4()
    run.side_effect = AttemptAlreadyGoneError(attempt_id)
    fail.side_effect = AttemptAlreadyGoneError(attempt_id)
    with caplog.at_level("INFO"):
        await worker._execute(attempt_id, sessions, VerificationWorkerConfig())
    assert "verification.attempt.deleted" in caplog.text
    assert "verification.worker.failed" not in caplog.text
