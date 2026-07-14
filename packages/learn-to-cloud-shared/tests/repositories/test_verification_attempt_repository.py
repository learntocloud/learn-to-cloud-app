"""Integration tests for VerificationAttemptRepository (CAS + reads)."""

from __future__ import annotations

import asyncio
from datetime import timedelta
from uuid import UUID, uuid4

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from learn_to_cloud_shared.models import (
    SubmissionValueKind,
    VerificationAttempt,
    VerificationAttemptOutcome,
    utcnow,
)
from learn_to_cloud_shared.repositories.user_repository import UserRepository
from learn_to_cloud_shared.repositories.verification_attempt_repository import (
    AttemptAlreadyValidatedError,
    VerificationAttemptRepository,
)
from learn_to_cloud_shared.submission_values import SubmittedValue

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
    requirement_uuid: UUID | None = None,
    created_at=None,
    started_at=None,
    outcome: str | None = None,
) -> UUID:
    attempt_id = attempt_id or uuid4()
    async with session_maker() as db:
        attempt = VerificationAttempt(
            id=attempt_id,
            user_id=USER_ID,
            requirement_uuid=requirement_uuid or uuid4(),
            snapshot_source="reconstructed",
            submission_value_kind="github_url",
            submitted_value="https://github.com/attemptrepo/repo",
            started_at=started_at,
            outcome=outcome,
            completed_at=utcnow() if outcome is not None else None,
        )
        if created_at is not None:
            attempt.created_at = created_at
        db.add(attempt)
        await db.commit()
    return attempt_id


def _submitted_value(
    value: str = "https://github.com/attemptrepo/repo",
) -> SubmittedValue:
    return SubmittedValue(kind=SubmissionValueKind.GITHUB_URL, github_url=value)


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


def _create_kwargs(
    *,
    id: UUID,
    requirement_uuid: UUID,
    submitted_value: SubmittedValue,
    legacy_job_id: UUID | None = None,
    requirement_snapshot: dict | None = None,
    requirement_snapshot_hash: str = "snapshot-hash",
) -> dict:
    """Shared kwargs for ``create_or_get_active`` so each test only overrides
    what it cares about."""
    return {
        "id": id,
        "user_id": USER_ID,
        "requirement_uuid": requirement_uuid,
        "artifact_schema_version": 1,
        "curriculum_version": 1,
        "content_hash": "content-hash",
        "requirement_snapshot": requirement_snapshot or {"slug": "test-requirement"},
        "requirement_snapshot_hash": requirement_snapshot_hash,
        "payload_version": 1,
        "github_username_snapshot": "attemptrepo",
        "submitted_value": submitted_value,
        "cloud_provider": None,
        "traceparent": None,
        "legacy_job_id": legacy_job_id if legacy_job_id is not None else id,
    }


async def test_create_or_get_active_creates_new_attempt(
    session_maker: async_sessionmaker[AsyncSession], user: int
) -> None:
    requirement_uuid = uuid4()
    attempt_id = uuid4()

    async with session_maker() as db:
        attempt, created = await VerificationAttemptRepository(db).create_or_get_active(
            **_create_kwargs(
                id=attempt_id,
                requirement_uuid=requirement_uuid,
                submitted_value=_submitted_value(),
            )
        )
        await db.commit()

    assert created is True
    assert attempt.id == attempt_id
    assert attempt.snapshot_source == "submitted"
    assert attempt.legacy_job_id == attempt_id
    assert attempt.submitted_value == "https://github.com/attemptrepo/repo"


async def test_create_or_get_active_returns_existing_active_attempt(
    session_maker: async_sessionmaker[AsyncSession], user: int
) -> None:
    requirement_uuid = uuid4()
    first_id = uuid4()
    second_id = uuid4()

    async with session_maker() as db:
        first, first_created = await VerificationAttemptRepository(
            db
        ).create_or_get_active(
            **_create_kwargs(
                id=first_id,
                requirement_uuid=requirement_uuid,
                submitted_value=_submitted_value(
                    "https://github.com/attemptrepo/first"
                ),
            )
        )
        await db.commit()

    async with session_maker() as db:
        second, second_created = await VerificationAttemptRepository(
            db
        ).create_or_get_active(
            **_create_kwargs(
                id=second_id,
                requirement_uuid=requirement_uuid,
                submitted_value=_submitted_value(
                    "https://github.com/attemptrepo/second"
                ),
            )
        )
        await db.commit()

    assert first_created is True
    assert second_created is False
    assert second.id == first.id
    assert second.submitted_value == "https://github.com/attemptrepo/first"

    async with session_maker() as db:
        count = await db.scalar(
            select(func.count())
            .select_from(VerificationAttempt)
            .where(VerificationAttempt.requirement_uuid == requirement_uuid)
        )
    assert count == 1


async def test_create_or_get_active_raises_for_succeeded_attempt(
    session_maker: async_sessionmaker[AsyncSession], user: int
) -> None:
    requirement_uuid = uuid4()
    await _insert_attempt(
        session_maker, requirement_uuid=requirement_uuid, outcome="succeeded"
    )

    async with session_maker() as db:
        with pytest.raises(AttemptAlreadyValidatedError):
            await VerificationAttemptRepository(db).create_or_get_active(
                **_create_kwargs(
                    id=uuid4(),
                    requirement_uuid=requirement_uuid,
                    submitted_value=_submitted_value(),
                )
            )


async def test_create_or_get_active_serializes_concurrent_submits(
    session_maker: async_sessionmaker[AsyncSession], user: int
) -> None:
    """Two concurrent submits for the same (user, requirement) must not
    both create an active attempt. The transaction-scoped advisory lock in
    ``create_or_get_active`` serializes them: the second caller blocks until
    the first commits, then sees the first's row under the lock and reuses
    it instead of creating a second active attempt."""
    requirement_uuid = uuid4()

    async def _submit(value: str) -> tuple[UUID, bool]:
        async with session_maker() as db:
            attempt, created = await VerificationAttemptRepository(
                db
            ).create_or_get_active(
                **_create_kwargs(
                    id=uuid4(),
                    requirement_uuid=requirement_uuid,
                    submitted_value=_submitted_value(
                        f"https://github.com/attemptrepo/{value}"
                    ),
                )
            )
            await db.commit()
        return attempt.id, created

    results = await asyncio.gather(_submit("first"), _submit("second"))

    created_flags = [created for _, created in results]
    assert created_flags.count(True) == 1
    assert created_flags.count(False) == 1
    # Both callers must agree on which attempt won the race.
    assert results[0][0] == results[1][0]

    async with session_maker() as db:
        count = await db.scalar(
            select(func.count())
            .select_from(VerificationAttempt)
            .where(VerificationAttempt.requirement_uuid == requirement_uuid)
        )
    assert count == 1


async def test_delete_active_removes_non_terminal_attempt(
    session_maker: async_sessionmaker[AsyncSession], user: int
) -> None:
    attempt_id = await _insert_attempt(session_maker)

    async with session_maker() as db:
        deleted = await VerificationAttemptRepository(db).delete_active(attempt_id)
        await db.commit()
    assert deleted is True

    async with session_maker() as db:
        status = await VerificationAttemptRepository(db).get_status(attempt_id)
    assert status is None


async def test_delete_active_refuses_terminal_attempt(
    session_maker: async_sessionmaker[AsyncSession], user: int
) -> None:
    attempt_id = await _insert_attempt(session_maker, outcome="succeeded")

    async with session_maker() as db:
        deleted = await VerificationAttemptRepository(db).delete_active(attempt_id)
    assert deleted is False

    async with session_maker() as db:
        status = await VerificationAttemptRepository(db).get_status(attempt_id)
    assert status is not None


async def test_delete_active_refuses_claimed_attempt(
    session_maker: async_sessionmaker[AsyncSession], user: int
) -> None:
    attempt_id = await _insert_attempt(session_maker, started_at=utcnow())

    async with session_maker() as db:
        deleted = await VerificationAttemptRepository(db).delete_active(attempt_id)
    assert deleted is False

    async with session_maker() as db:
        status = await VerificationAttemptRepository(db).get_status(attempt_id)
    assert status is not None
    assert status.started_at is not None


# ---------------------------------------------------------------------------
# PR6 progress/gating/card/stats reads
# ---------------------------------------------------------------------------


async def test_get_succeeded_requirement_uuids_only_counts_succeeded(
    session_maker: async_sessionmaker[AsyncSession], user: int
) -> None:
    succeeded_req = uuid4()
    failed_req = uuid4()
    await _insert_attempt(
        session_maker, requirement_uuid=succeeded_req, outcome="succeeded"
    )
    await _insert_attempt(session_maker, requirement_uuid=failed_req, outcome="failed")

    async with session_maker() as db:
        result = await VerificationAttemptRepository(
            db
        ).get_succeeded_requirement_uuids(USER_ID)

    assert result == {succeeded_req}


async def test_count_succeeded_for_requirements_filters_to_candidates(
    session_maker: async_sessionmaker[AsyncSession], user: int
) -> None:
    succeeded_req = uuid4()
    other_succeeded_req = uuid4()
    await _insert_attempt(
        session_maker, requirement_uuid=succeeded_req, outcome="succeeded"
    )
    await _insert_attempt(
        session_maker, requirement_uuid=other_succeeded_req, outcome="succeeded"
    )

    async with session_maker() as db:
        count = await VerificationAttemptRepository(
            db
        ).count_succeeded_for_requirements(USER_ID, [succeeded_req])
    assert count == 1


async def test_count_succeeded_for_requirements_empty_input_returns_zero(
    session_maker: async_sessionmaker[AsyncSession], user: int
) -> None:
    async with session_maker() as db:
        count = await VerificationAttemptRepository(
            db
        ).count_succeeded_for_requirements(USER_ID, [])
    assert count == 0


async def test_are_all_requirements_succeeded_true_when_all_succeeded(
    session_maker: async_sessionmaker[AsyncSession], user: int
) -> None:
    a, b = uuid4(), uuid4()
    await _insert_attempt(session_maker, requirement_uuid=a, outcome="succeeded")
    await _insert_attempt(session_maker, requirement_uuid=b, outcome="succeeded")
    async with session_maker() as db:
        assert await VerificationAttemptRepository(db).are_all_requirements_succeeded(
            USER_ID, [a, b]
        )


async def test_are_all_requirements_succeeded_false_when_one_missing(
    session_maker: async_sessionmaker[AsyncSession], user: int
) -> None:
    a, b = uuid4(), uuid4()
    await _insert_attempt(session_maker, requirement_uuid=a, outcome="succeeded")
    async with session_maker() as db:
        assert not await VerificationAttemptRepository(
            db
        ).are_all_requirements_succeeded(USER_ID, [a, b])


async def test_are_all_requirements_succeeded_empty_list_is_true(
    session_maker: async_sessionmaker[AsyncSession], user: int
) -> None:
    async with session_maker() as db:
        assert await VerificationAttemptRepository(db).are_all_requirements_succeeded(
            USER_ID, []
        )


async def test_get_requirement_uuids_with_any_attempt_includes_active_and_terminal(
    session_maker: async_sessionmaker[AsyncSession], user: int
) -> None:
    active_req = uuid4()
    terminal_req = uuid4()
    no_attempt_req = uuid4()
    await _insert_attempt(session_maker, requirement_uuid=active_req)
    await _insert_attempt(
        session_maker, requirement_uuid=terminal_req, outcome="failed"
    )
    async with session_maker() as db:
        result = await VerificationAttemptRepository(
            db
        ).get_requirement_uuids_with_any_attempt(
            USER_ID, [active_req, terminal_req, no_attempt_req]
        )
    assert result == {active_req, terminal_req}


async def test_get_requirement_uuids_with_any_attempt_empty_input(
    session_maker: async_sessionmaker[AsyncSession], user: int
) -> None:
    async with session_maker() as db:
        result = await VerificationAttemptRepository(
            db
        ).get_requirement_uuids_with_any_attempt(USER_ID, [])
    assert result == set()


async def test_get_active_for_requirements_excludes_terminal(
    session_maker: async_sessionmaker[AsyncSession], user: int
) -> None:
    active_req = uuid4()
    terminal_req = uuid4()
    active_id = await _insert_attempt(session_maker, requirement_uuid=active_req)
    await _insert_attempt(
        session_maker, requirement_uuid=terminal_req, outcome="succeeded"
    )
    async with session_maker() as db:
        rows = await VerificationAttemptRepository(db).get_active_for_requirements(
            USER_ID, [active_req, terminal_req]
        )
    assert {row.requirement_uuid for row in rows} == {active_req}
    assert rows[0].id == active_id


async def test_get_latest_terminal_for_requirements_returns_newest_and_skips_active(
    session_maker: async_sessionmaker[AsyncSession], user: int
) -> None:
    req = uuid4()
    now = utcnow()
    await _insert_attempt(
        session_maker,
        requirement_uuid=req,
        created_at=now - timedelta(hours=2),
        outcome="failed",
    )
    latest_id = await _insert_attempt(
        session_maker,
        requirement_uuid=req,
        created_at=now - timedelta(hours=1),
        outcome="succeeded",
    )
    # A newer *active* attempt for the same requirement must not shadow the
    # latest terminal one -- active attempts are excluded from this read.
    await _insert_attempt(session_maker, requirement_uuid=req, created_at=now)

    async with session_maker() as db:
        rows = await VerificationAttemptRepository(
            db
        ).get_latest_terminal_for_requirements(USER_ID, [req])

    assert len(rows) == 1
    assert rows[0].id == latest_id
    assert rows[0].outcome == "succeeded"


async def test_get_latest_terminal_for_requirements_empty_input(
    session_maker: async_sessionmaker[AsyncSession], user: int
) -> None:
    async with session_maker() as db:
        rows = await VerificationAttemptRepository(
            db
        ).get_latest_terminal_for_requirements(USER_ID, [])
    assert rows == []


class TestListPhaseCompletions:
    async def test_succeeded_attempt_counts_as_completion(
        self, session_maker: async_sessionmaker[AsyncSession], user: int
    ) -> None:
        req = uuid4()
        await _insert_attempt(session_maker, requirement_uuid=req, outcome="succeeded")

        async with session_maker() as db:
            completions = await VerificationAttemptRepository(
                db
            ).list_phase_completions({0: 1}, {req: 0})

        assert (0, USER_ID) in completions

    async def test_failed_attempt_does_not_count(
        self, session_maker: async_sessionmaker[AsyncSession], user: int
    ) -> None:
        req = uuid4()
        await _insert_attempt(session_maker, requirement_uuid=req, outcome="failed")

        async with session_maker() as db:
            completions = await VerificationAttemptRepository(
                db
            ).list_phase_completions({0: 1}, {req: 0})

        assert (0, USER_ID) not in completions

    async def test_partial_completion_excluded(
        self, session_maker: async_sessionmaker[AsyncSession], user: int
    ) -> None:
        req_a, req_b = uuid4(), uuid4()
        await _insert_attempt(
            session_maker, requirement_uuid=req_a, outcome="succeeded"
        )
        # req_b never attempted -- phase 0 needs both to complete.

        async with session_maker() as db:
            completions = await VerificationAttemptRepository(
                db
            ).list_phase_completions({0: 2}, {req_a: 0, req_b: 0})

        assert (0, USER_ID) not in completions

    async def test_empty_counts_returns_empty(
        self, session_maker: async_sessionmaker[AsyncSession], user: int
    ) -> None:
        async with session_maker() as db:
            assert (
                await VerificationAttemptRepository(db).list_phase_completions({}, {})
                == []
            )

    async def test_stale_requirement_uuid_is_ignored(
        self, session_maker: async_sessionmaker[AsyncSession], user: int
    ) -> None:
        """A succeeded attempt for a requirement UUID absent from the phase
        map (as if the catalog no longer knows about it) must not produce a
        phantom completion."""
        req = uuid4()
        await _insert_attempt(session_maker, requirement_uuid=req, outcome="succeeded")

        async with session_maker() as db:
            completions = await VerificationAttemptRepository(
                db
            ).list_phase_completions({0: 1}, {})

        assert (0, USER_ID) not in completions
