"""Integration tests for VerificationAttemptRepository (CAS + reads)."""

from __future__ import annotations

from datetime import timedelta
from uuid import UUID, uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from learn_to_cloud_shared.models import (
    VerificationAttempt,
    VerificationAttemptOutcome,
    utcnow,
)
from learn_to_cloud_shared.repositories.user_repository import UserRepository
from learn_to_cloud_shared.repositories.verification_attempt_repository import (
    VerificationAttemptRepository,
)

pytestmark = pytest.mark.integration

USER_ID = 84001


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
        await UserRepository(db).upsert(USER_ID, github_username="attemptrepo")
        await db.commit()
    return USER_ID


async def _insert_attempt(
    session_maker: async_sessionmaker[AsyncSession],
    *,
    attempt_id: UUID | None = None,
    created_at=None,
    outcome: str | None = None,
) -> UUID:
    attempt_id = attempt_id or uuid4()
    async with session_maker() as db:
        attempt = VerificationAttempt(
            id=attempt_id,
            user_id=USER_ID,
            requirement_uuid=uuid4(),
            snapshot_source="reconstructed",
            submission_value_kind="github_url",
            submitted_value="https://github.com/attemptrepo/repo",
            outcome=outcome,
            completed_at=utcnow() if outcome is not None else None,
        )
        if created_at is not None:
            attempt.created_at = created_at
        db.add(attempt)
        await db.commit()
    return attempt_id


async def test_finalize_sets_terminal_state(
    session_maker: async_sessionmaker[AsyncSession], user: int
) -> None:
    attempt_id = await _insert_attempt(session_maker)
    async with session_maker() as db:
        result = await VerificationAttemptRepository(db).finalize(
            attempt_id,
            outcome=VerificationAttemptOutcome.SUCCEEDED,
            error_code="verification_succeeded",
            validation_message=None,
            terminal_source="orchestrator",
            feedback_json=[{"task": "a"}],
        )
        await db.commit()
    assert result.won is True
    assert result.state.outcome == "succeeded"
    assert result.state.completed_at is not None


async def test_finalize_is_compare_and_set(
    session_maker: async_sessionmaker[AsyncSession], user: int
) -> None:
    attempt_id = await _insert_attempt(session_maker)
    async with session_maker() as db:
        first = await VerificationAttemptRepository(db).finalize(
            attempt_id,
            outcome=VerificationAttemptOutcome.SUCCEEDED,
            error_code="verification_succeeded",
            validation_message=None,
            terminal_source="orchestrator",
            feedback_json=None,
        )
        await db.commit()

    # A competing finalizer with a different outcome must not overwrite.
    async with session_maker() as db:
        second = await VerificationAttemptRepository(db).finalize(
            attempt_id,
            outcome=VerificationAttemptOutcome.SERVER_ERROR,
            error_code="server_error",
            validation_message="late",
            terminal_source="reconciler",
            feedback_json=None,
        )
        await db.commit()

    assert first.won is True
    assert second.won is False
    assert second.state.outcome == "succeeded"
    assert second.state.terminal_source == "orchestrator"


async def test_get_prepare_state_and_status(
    session_maker: async_sessionmaker[AsyncSession], user: int
) -> None:
    attempt_id = await _insert_attempt(session_maker)
    async with session_maker() as db:
        repo = VerificationAttemptRepository(db)
        prepare = await repo.get_prepare_state(attempt_id)
        status = await repo.get_status(attempt_id)
    assert prepare is not None
    assert prepare.submission_value_kind == "github_url"
    assert prepare.outcome is None
    assert status is not None
    assert status.outcome is None


async def test_mark_started_is_idempotent(
    session_maker: async_sessionmaker[AsyncSession], user: int
) -> None:
    attempt_id = await _insert_attempt(session_maker)
    first_started_at = utcnow()
    async with session_maker() as db:
        repo = VerificationAttemptRepository(db)
        assert await repo.mark_started(attempt_id, started_at=first_started_at)
        await db.commit()

    async with session_maker() as db:
        repo = VerificationAttemptRepository(db)
        assert not await repo.mark_started(
            attempt_id, started_at=first_started_at + timedelta(minutes=1)
        )
        status = await repo.get_status(attempt_id)
    assert status is not None
    assert status.started_at == first_started_at


async def test_list_active_older_than_filters(
    session_maker: async_sessionmaker[AsyncSession], user: int
) -> None:
    now = utcnow()
    old_active = await _insert_attempt(
        session_maker, created_at=now - timedelta(hours=2)
    )
    await _insert_attempt(session_maker, created_at=now - timedelta(minutes=1))
    await _insert_attempt(
        session_maker, created_at=now - timedelta(hours=3), outcome="succeeded"
    )

    async with session_maker() as db:
        rows = await VerificationAttemptRepository(db).list_active_older_than(
            now - timedelta(hours=1), limit=10
        )
    ids = {row.id for row in rows}
    assert old_active in ids
    assert all(row.outcome is None for row in rows)
    assert len(ids) == 1


async def test_list_active_older_than_uses_started_at_when_present(
    session_maker: async_sessionmaker[AsyncSession], user: int
) -> None:
    now = utcnow()
    attempt_id = await _insert_attempt(
        session_maker, created_at=now - timedelta(hours=2)
    )
    async with session_maker() as db:
        repo = VerificationAttemptRepository(db)
        assert await repo.mark_started(attempt_id, started_at=now)
        await db.commit()

    async with session_maker() as db:
        rows = await VerificationAttemptRepository(db).list_active_older_than(
            now - timedelta(hours=1), limit=10
        )
    assert attempt_id not in {row.id for row in rows}
