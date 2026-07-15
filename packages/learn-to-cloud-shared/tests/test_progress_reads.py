"""Integration tests for authoritative progress reads."""

from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from learn_to_cloud_shared.models import (
    LearnerStepCompletion,
    User,
    VerificationAttempt,
    utcnow,
)
from learn_to_cloud_shared.progress_reads import (
    are_all_requirements_succeeded,
    resolve_completed_step_uuids,
    resolve_succeeded_requirement_uuids,
)

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]


async def test_resolves_only_candidate_completed_steps(
    db_session: AsyncSession,
) -> None:
    user_id = 81001
    included = uuid4()
    other = uuid4()
    db_session.add(User(id=user_id, github_username="progress-step"))
    await db_session.flush()
    db_session.add_all(
        [
            LearnerStepCompletion(user_id=user_id, step_uuid=included),
            LearnerStepCompletion(user_id=user_id, step_uuid=other),
        ]
    )
    await db_session.flush()

    completed = await resolve_completed_step_uuids(
        db_session, user_id, [included, uuid4()]
    )

    assert completed == {included}


async def test_resolves_only_succeeded_current_requirements(
    db_session: AsyncSession,
) -> None:
    user_id = 81002
    succeeded = uuid4()
    failed = uuid4()
    db_session.add(User(id=user_id, github_username="progress-requirement"))
    await db_session.flush()
    db_session.add_all(
        [
            VerificationAttempt(
                user_id=user_id,
                requirement_uuid=succeeded,
                snapshot_source="reconstructed",
                submission_value_kind="text",
                submitted_value="done",
                outcome="succeeded",
                completed_at=utcnow(),
            ),
            VerificationAttempt(
                user_id=user_id,
                requirement_uuid=failed,
                snapshot_source="reconstructed",
                submission_value_kind="text",
                submitted_value="not yet",
                outcome="failed",
                completed_at=utcnow(),
            ),
        ]
    )
    await db_session.flush()

    result = await resolve_succeeded_requirement_uuids(
        db_session, user_id, [succeeded, failed, uuid4()]
    )

    assert result == {succeeded}


async def test_all_requirements_succeeded_handles_empty_and_incomplete_sets(
    db_session: AsyncSession,
) -> None:
    user_id = 81003
    succeeded = uuid4()
    missing = uuid4()
    db_session.add(User(id=user_id, github_username="progress-all"))
    await db_session.flush()
    db_session.add(
        VerificationAttempt(
            user_id=user_id,
            requirement_uuid=succeeded,
            snapshot_source="reconstructed",
            submission_value_kind="text",
            submitted_value="done",
            outcome="succeeded",
            completed_at=utcnow(),
        )
    )
    await db_session.flush()

    assert await are_all_requirements_succeeded(db_session, user_id, []) is True
    assert (
        await are_all_requirements_succeeded(db_session, user_id, [succeeded]) is True
    )
    assert (
        await are_all_requirements_succeeded(db_session, user_id, [succeeded, missing])
        is False
    )
