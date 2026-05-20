"""Integration tests for the sync verification execution path.

Exercises ``execute_sync_submission_validation`` against a real Postgres
test database so the ``pg_try_advisory_xact_lock``-based dedupe contract
is verified end-to-end (mocking the lock would only assert that the
mock is called).
"""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from learn_to_cloud_shared.models import Submission, SubmissionType
from learn_to_cloud_shared.repositories.user_repository import UserRepository
from learn_to_cloud_shared.schemas import HandsOnRequirement, ValidationResult
from learn_to_cloud_shared.verification.execution import (
    SubmissionAlreadyInFlightError,
    execute_sync_submission_validation,
)

pytestmark = pytest.mark.integration

USER_ID = 92001
REQUIREMENT_ID = "sync-execution-test"
PHASE_ID = 0


@pytest.fixture()
def session_maker(test_engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(
        bind=test_engine,
        class_=AsyncSession,
        expire_on_commit=False,
        autoflush=False,
    )


def _requirement(
    submission_type: SubmissionType = SubmissionType.GITHUB_PROFILE,
) -> HandsOnRequirement:
    return HandsOnRequirement(
        id=REQUIREMENT_ID,
        submission_type=submission_type,
        name="Sync Execution Test",
        description="Test requirement",
    )


async def _seed_user(session_maker: async_sessionmaker[AsyncSession]) -> None:
    async with session_maker() as db:
        await UserRepository(db).upsert(USER_ID, github_username="syncuser")
        await db.commit()


async def _count_submissions(
    session_maker: async_sessionmaker[AsyncSession],
) -> int:
    async with session_maker() as db:
        result = await db.execute(
            select(Submission).where(Submission.user_id == USER_ID)
        )
        return len(list(result.scalars().all()))


async def test_sync_validation_persists_submission(
    session_maker: async_sessionmaker[AsyncSession],
) -> None:
    """Happy path: validator returns success, ``Submission`` row is written."""
    await _seed_user(session_maker)

    with patch(
        "learn_to_cloud_shared.verification.execution.validate_submission",
        new=AsyncMock(
            return_value=ValidationResult(
                is_valid=True,
                message="ok",
                verification_completed=True,
            )
        ),
    ):
        result = await execute_sync_submission_validation(
            session_maker=session_maker,
            user_id=USER_ID,
            requirement=_requirement(),
            phase_id=PHASE_ID,
            submitted_value="https://github.com/syncuser",
            github_username="syncuser",
        )

    assert result.is_valid is True
    assert result.submission.is_validated is True
    assert await _count_submissions(session_maker) == 1


async def test_sync_validation_persists_failure(
    session_maker: async_sessionmaker[AsyncSession],
) -> None:
    """User-correctable failure path: row is written with is_validated=False."""
    await _seed_user(session_maker)

    with patch(
        "learn_to_cloud_shared.verification.execution.validate_submission",
        new=AsyncMock(
            return_value=ValidationResult(
                is_valid=False,
                message="GitHub username does not match",
                verification_completed=True,
            )
        ),
    ):
        result = await execute_sync_submission_validation(
            session_maker=session_maker,
            user_id=USER_ID,
            requirement=_requirement(),
            phase_id=PHASE_ID,
            submitted_value="https://github.com/wronguser",
            github_username="syncuser",
        )

    assert result.is_valid is False
    assert result.submission.is_validated is False
    assert result.submission.verification_completed is True
    assert await _count_submissions(session_maker) == 1


async def test_sync_validation_rolls_back_on_validator_exception(
    session_maker: async_sessionmaker[AsyncSession],
) -> None:
    """A crash inside the validator must not leave a half-written Submission.

    The transaction wraps lock + validate + persist, so a raised exception
    rolls back the whole thing and the advisory lock is released.
    """
    await _seed_user(session_maker)

    with patch(
        "learn_to_cloud_shared.verification.execution.validate_submission",
        new=AsyncMock(side_effect=RuntimeError("validator crashed")),
    ):
        with pytest.raises(RuntimeError, match="validator crashed"):
            await execute_sync_submission_validation(
                session_maker=session_maker,
                user_id=USER_ID,
                requirement=_requirement(),
                phase_id=PHASE_ID,
                submitted_value="https://github.com/syncuser",
                github_username="syncuser",
            )

    assert await _count_submissions(session_maker) == 0

    # Lock was released, so a follow-up submit succeeds.
    with patch(
        "learn_to_cloud_shared.verification.execution.validate_submission",
        new=AsyncMock(
            return_value=ValidationResult(
                is_valid=True,
                message="ok",
                verification_completed=True,
            )
        ),
    ):
        await execute_sync_submission_validation(
            session_maker=session_maker,
            user_id=USER_ID,
            requirement=_requirement(),
            phase_id=PHASE_ID,
            submitted_value="https://github.com/syncuser",
            github_username="syncuser",
        )

    assert await _count_submissions(session_maker) == 1


async def test_concurrent_submits_for_same_requirement_dedupe(
    session_maker: async_sessionmaker[AsyncSession],
) -> None:
    """Two concurrent submits for the same (user, requirement) must not
    both run the validator and persist duplicate Submission rows.

    Uses an asyncio.Event to keep the first request inside the validator
    long enough for the second request to race past the lock check.
    """
    await _seed_user(session_maker)

    started = asyncio.Event()
    release = asyncio.Event()

    async def _slow_validator(*_args, **_kwargs):
        started.set()
        await release.wait()
        return ValidationResult(
            is_valid=True,
            message="ok",
            verification_completed=True,
        )

    with patch(
        "learn_to_cloud_shared.verification.execution.validate_submission",
        new=_slow_validator,
    ):
        first = asyncio.create_task(
            execute_sync_submission_validation(
                session_maker=session_maker,
                user_id=USER_ID,
                requirement=_requirement(),
                phase_id=PHASE_ID,
                submitted_value="https://github.com/syncuser",
                github_username="syncuser",
            )
        )

        # Wait until the first request is past the lock and inside the validator.
        await asyncio.wait_for(started.wait(), timeout=5.0)

        # The second request must immediately bail out with
        # SubmissionAlreadyInFlightError — not block, not race-write a row.
        with pytest.raises(SubmissionAlreadyInFlightError):
            await execute_sync_submission_validation(
                session_maker=session_maker,
                user_id=USER_ID,
                requirement=_requirement(),
                phase_id=PHASE_ID,
                submitted_value="https://github.com/syncuser",
                github_username="syncuser",
            )

        # Let the first request complete; it should succeed and write a row.
        release.set()
        first_result = await asyncio.wait_for(first, timeout=5.0)
        assert first_result.is_valid is True

    assert await _count_submissions(session_maker) == 1


async def test_advisory_lock_keyed_per_requirement(
    session_maker: async_sessionmaker[AsyncSession],
) -> None:
    """The lock is per ``(user_id, requirement_id)``, so a concurrent
    submit for a *different* requirement must NOT be blocked."""
    other_requirement_id = f"{REQUIREMENT_ID}-other"
    await _seed_user(session_maker)

    started = asyncio.Event()
    release = asyncio.Event()

    async def _slow_validator(*_args, **_kwargs):
        started.set()
        await release.wait()
        return ValidationResult(
            is_valid=True,
            message="ok",
            verification_completed=True,
        )

    async def _fast_validator(*_args, **_kwargs):
        return ValidationResult(
            is_valid=True,
            message="ok",
            verification_completed=True,
        )

    # First submit holds the lock for REQUIREMENT_ID.
    with patch(
        "learn_to_cloud_shared.verification.execution.validate_submission",
        new=_slow_validator,
    ):
        first = asyncio.create_task(
            execute_sync_submission_validation(
                session_maker=session_maker,
                user_id=USER_ID,
                requirement=_requirement(),
                phase_id=PHASE_ID,
                submitted_value="https://github.com/syncuser",
                github_username="syncuser",
            )
        )
        await asyncio.wait_for(started.wait(), timeout=5.0)

        # Different requirement → different lock key → must proceed immediately.
        other_requirement = HandsOnRequirement(
            id=other_requirement_id,
            submission_type=SubmissionType.GITHUB_PROFILE,
            name="Other",
            description="Other",
        )
        with patch(
            "learn_to_cloud_shared.verification.execution.validate_submission",
            new=_fast_validator,
        ):
            second_result = await execute_sync_submission_validation(
                session_maker=session_maker,
                user_id=USER_ID,
                requirement=other_requirement,
                phase_id=PHASE_ID,
                submitted_value="https://github.com/syncuser",
                github_username="syncuser",
            )
        assert second_result.is_valid is True

        release.set()
        await asyncio.wait_for(first, timeout=5.0)

    assert await _count_submissions(session_maker) == 2


async def test_advisory_lock_uses_pg_try_advisory_xact_lock(
    session_maker: async_sessionmaker[AsyncSession],
) -> None:
    """The lock helper uses Postgres' transactional advisory lock — the
    test also reaches into pg_locks to confirm zero advisory locks remain
    after the function returns. Catches regressions where someone swaps
    in pg_advisory_lock (session-level) by mistake."""
    await _seed_user(session_maker)

    with patch(
        "learn_to_cloud_shared.verification.execution.validate_submission",
        new=AsyncMock(
            return_value=ValidationResult(
                is_valid=True,
                message="ok",
                verification_completed=True,
            )
        ),
    ):
        await execute_sync_submission_validation(
            session_maker=session_maker,
            user_id=USER_ID,
            requirement=_requirement(),
            phase_id=PHASE_ID,
            submitted_value="https://github.com/syncuser",
            github_username="syncuser",
        )

    async with session_maker() as db:
        held = await db.scalar(
            text(
                "SELECT COUNT(*) FROM pg_locks WHERE locktype = 'advisory' AND granted"
            )
        )
        assert held == 0
