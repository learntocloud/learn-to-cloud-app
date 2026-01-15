"""Tests for admin bypass behavior (content unlocking).

Admins should not be blocked by step-level sequential unlock rules.
"""

import pytest

from services.steps import StepNotUnlockedError, complete_step, get_topic_step_progress


@pytest.mark.asyncio
async def test_non_admin_cannot_complete_step_out_of_order(db_session, test_user):
    with pytest.raises(StepNotUnlockedError):
        await complete_step(
            db_session,
            test_user.id,
            "phase0-topic0",
            3,
            is_admin=False,
        )


@pytest.mark.asyncio
async def test_admin_can_complete_step_out_of_order(db_session, test_user):
    test_user.is_admin = True
    db_session.add(test_user)
    await db_session.commit()

    result = await complete_step(
        db_session,
        test_user.id,
        "phase0-topic0",
        3,
        is_admin=True,
    )

    assert result.topic_id == "phase0-topic0"
    assert result.step_order == 3


@pytest.mark.asyncio
async def test_admin_step_progress_unlocks_all_steps(db_session, test_user):
    progress = await get_topic_step_progress(
        db_session,
        test_user.id,
        "phase0-topic0",
        10,
        is_admin=True,
    )

    assert progress.total_steps == 10
    assert progress.next_unlocked_step == 10
