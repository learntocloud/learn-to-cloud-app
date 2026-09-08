"""PostgreSQL claims coordinate API replicas without replaying started work."""

from datetime import timedelta
from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker

from learn_to_cloud_shared.models import VerificationAttempt, utcnow
from learn_to_cloud_shared.repositories.user_repository import UserRepository
from learn_to_cloud_shared.repositories.verification_attempt_repository import (
    VerificationAttemptRepository,
)
from learn_to_cloud_shared.verification_attempt_executor import (
    expire_verification_attempts,
)

pytestmark = pytest.mark.integration


@pytest.fixture
async def sessions(test_engine):
    sessions = async_sessionmaker(test_engine, expire_on_commit=False)
    async with sessions() as db:
        await UserRepository(db).upsert(85001, github_username="workerqueue")
        await db.commit()
    return sessions


async def _insert(sessions, **overrides):
    values = {
        "id": uuid4(),
        "user_id": 85001,
        "requirement_uuid": uuid4(),
        "snapshot_source": "submitted",
        "requirement_snapshot": {},
        "requirement_snapshot_hash": "hash",
        "submission_value_kind": "github_url",
        "submitted_value": "https://github.com/workerqueue/repo",
        "created_at": utcnow() - timedelta(seconds=10),
    }
    values.update(overrides)
    async with sessions() as db:
        db.add(VerificationAttempt(**values))
        await db.commit()
    return values["id"]


async def test_parallel_claims_skip_locked_attempts_and_never_reclaim(sessions):
    first_id = await _insert(sessions, created_at=utcnow() - timedelta(seconds=20))
    second_id = await _insert(sessions)
    cutoff = utcnow() - timedelta(seconds=600)
    async with sessions() as first, sessions() as second:
        claimed_first = await VerificationAttemptRepository(first).claim_pending(
            queued_after=cutoff
        )
        claimed_second = await VerificationAttemptRepository(second).claim_pending(
            queued_after=cutoff
        )
        assert claimed_first == first_id
        assert claimed_second == second_id
        await first.commit()
        await second.commit()
    async with sessions() as db:
        repo = VerificationAttemptRepository(db)
        assert await repo.claim_pending(queued_after=cutoff) is None
        status = await repo.get_status(first_id)
        assert status.started_at is not None


async def test_rolled_back_claim_remains_available(sessions):
    attempt_id = await _insert(sessions)
    cutoff = utcnow() - timedelta(seconds=600)
    async with sessions() as db:
        assert (
            await VerificationAttemptRepository(db).claim_pending(queued_after=cutoff)
            == attempt_id
        )
        await db.rollback()
    async with sessions() as db:
        assert (
            await VerificationAttemptRepository(db).claim_pending(queued_after=cutoff)
            == attempt_id
        )


async def test_claim_excludes_terminal_legacy_started_and_expired_rows(sessions):
    await _insert(sessions, outcome="succeeded", completed_at=utcnow())
    await _insert(sessions, snapshot_source="reconstructed")
    await _insert(sessions, started_at=utcnow())
    await _insert(sessions, created_at=utcnow() - timedelta(seconds=601))
    async with sessions() as db:
        assert (
            await VerificationAttemptRepository(db).claim_pending(
                queued_after=utcnow() - timedelta(seconds=600)
            )
            is None
        )


async def test_expiry_is_terminal_and_logs_once_after_commit(sessions, caplog):
    old = utcnow() - timedelta(seconds=700)
    queued = await _insert(sessions, created_at=old)
    started = await _insert(sessions, created_at=old, started_at=old)
    completed = await _insert(
        sessions, created_at=old, outcome="succeeded", completed_at=old
    )
    fresh = await _insert(sessions)
    cutoffs = {
        "queued_before": utcnow() - timedelta(seconds=600),
        "started_before": utcnow() - timedelta(seconds=190),
        "session_maker": sessions,
    }
    with caplog.at_level("INFO"):
        await expire_verification_attempts(**cutoffs)
        await expire_verification_attempts(**cutoffs)
    async with sessions() as db:
        repo = VerificationAttemptRepository(db)
        for attempt_id in (queued, started):
            status = await db.get(VerificationAttempt, attempt_id)
            assert status is not None
            assert status.outcome == "server_error"
            assert status.error_code == "verification_timeout"
        assert (await repo.get_status(completed)).outcome == "succeeded"
        assert (await repo.get_status(fresh)).outcome is None
    completions = [
        r for r in caplog.records if r.message == "verification.attempt.completed"
    ]
    stuck = [r for r in caplog.records if r.message == "verification.attempt.stuck"]
    assert len(completions) == 2
    assert {r.__dict__["verification.stuck.reason"] for r in stuck} == {
        "queued_beyond_limit",
        "execution_beyond_limit",
    }
