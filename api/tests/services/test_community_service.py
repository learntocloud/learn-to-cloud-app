"""Integration tests for the public community payload."""

from unittest.mock import AsyncMock, patch

import pytest
from learn_to_cloud_shared.content_catalog import get_curriculum_catalog
from learn_to_cloud_shared.content_service import get_requirement_counts_by_phase
from learn_to_cloud_shared.models import User, VerificationAttempt, utcnow
from sqlalchemy.ext.asyncio import AsyncSession

from learn_to_cloud.services.community_service import get_community_page_data

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]


async def _complete_phase(
    db: AsyncSession,
    *,
    user_id: int,
    phase_order: int,
) -> None:
    catalog = get_curriculum_catalog()
    requirement_uuids = [
        requirement_uuid
        for requirement_uuid, order in catalog.phase_order_by_requirement_uuid.items()
        if order == phase_order
    ]
    for requirement_uuid in requirement_uuids:
        db.add(
            VerificationAttempt(
                user_id=user_id,
                requirement_uuid=requirement_uuid,
                snapshot_source="reconstructed",
                submission_value_kind="text",
                submitted_value="historical verification",
                outcome="succeeded",
                completed_at=utcnow(),
            )
        )
    await db.flush()


async def test_graduates_are_full_curriculum_completers(
    db_session: AsyncSession,
) -> None:
    counts = get_requirement_counts_by_phase()
    completable = sorted(order for order, count in counts.items() if count > 0)
    db_session.add_all(
        [
            User(id=60001, github_username="grad"),
            User(id=60002, github_username="partial"),
        ]
    )
    await db_session.flush()

    for order in completable:
        await _complete_phase(db_session, user_id=60001, phase_order=order)
    await _complete_phase(db_session, user_id=60002, phase_order=completable[0])

    with patch(
        "learn_to_cloud.services.community_service.get_latest_curriculum_commits",
        new=AsyncMock(return_value=[]),
    ):
        community = await get_community_page_data(db_session)

    assert [member.github_username for member in community.graduates] == ["grad"]


async def test_funnel_uses_authoritative_attempts_and_excludes_empty_phases(
    db_session: AsyncSession,
) -> None:
    counts = get_requirement_counts_by_phase()
    first_completable = min(order for order, count in counts.items() if count > 0)
    db_session.add(User(id=60003, github_username="funnel"))
    await db_session.flush()
    await _complete_phase(db_session, user_id=60003, phase_order=first_completable)

    with patch(
        "learn_to_cloud.services.community_service.get_latest_curriculum_commits",
        new=AsyncMock(return_value=[]),
    ):
        community = await get_community_page_data(db_session)

    assert community.total_accounts == 1
    assert community.funnel[0].label == "Total accounts"
    assert community.funnel[1].count == 1
    assert len(community.funnel) == 1 + sum(count > 0 for count in counts.values())
