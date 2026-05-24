"""Integration tests for content_sync.sync_curriculum_to_db (issue #463)."""

from __future__ import annotations

from datetime import datetime
from unittest.mock import patch
from uuid import UUID, uuid4

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from learn_to_cloud_shared.content_sync import (
    ContentSyncError,
    sync_curriculum_to_db,
)
from learn_to_cloud_shared.models import (
    CurriculumPhase,
    CurriculumRequirement,
)
from learn_to_cloud_shared.schemas import (
    HandsOnRequirementAdapter,
    LearningObjective,
    LearningStep,
    Phase,
    PhaseHandsOnVerificationOverview,
    Topic,
)

pytestmark = pytest.mark.integration


def _make_step(uuid_str: str, order: int) -> LearningStep:
    return LearningStep(
        uuid=UUID(uuid_str),
        slug=f"step-{order}",
        order=order,
        action="Read:",
        title=f"Step {order}",
    )


def _make_objective(uuid_str: str, order: int) -> LearningObjective:
    return LearningObjective(
        uuid=UUID(uuid_str),
        text=f"Objective {order}",
        order=order,
    )


def _make_topic(uuid_str: str, slug: str, order: int = 0) -> Topic:
    return Topic(
        uuid=UUID(uuid_str),
        slug=slug,
        name=slug.title(),
        description=f"Topic {slug}",
        order=order,
        learning_steps=[
            _make_step("00000000-0000-0000-0000-000000000010", 1),
        ],
        learning_objectives=[
            _make_objective("00000000-0000-0000-0000-000000000020", 1),
        ],
    )


def _make_requirement(uuid_str: str, req_id: str) -> object:
    """Build a GithubProfileRequirement via the adapter."""
    return HandsOnRequirementAdapter.validate_python(
        {
            "uuid": uuid_str,
            "slug": req_id,
            "submission_type": "github_profile",
            "name": f"Requirement {req_id}",
            "description": "Test requirement",
        }
    )


def _make_phase(
    uuid_str: str = "00000000-0000-0000-0000-000000000001",
    slug: str = "phase0",
    phase_int_id: int = 0,
    topic: Topic | None = None,
    requirement_uuid: str | None = None,
    requirement_id: str = "github-profile",
) -> Phase:
    req = None
    if requirement_uuid:
        req = PhaseHandsOnVerificationOverview(
            requirement_slugs=[requirement_id],
            requirements=[_make_requirement(requirement_uuid, requirement_id)],
        )
    return Phase(
        uuid=UUID(uuid_str),
        slug=slug,
        name=slug.title(),
        description=f"Description for {slug}",
        short_description=f"Short {slug}",
        order=phase_int_id,
        topic_slugs=[topic.slug] if topic else [],
        topics=[topic] if topic else [],
        hands_on_verification=req,
    )


@pytest.fixture()
def fresh_curriculum() -> tuple[Phase, ...]:
    """A minimal but realistic curriculum: one phase, one topic, one requirement."""
    topic = _make_topic(
        "00000000-0000-0000-0000-000000000002",
        slug="basics",
    )
    return (
        _make_phase(
            topic=topic,
            requirement_uuid="00000000-0000-0000-0000-000000000003",
        ),
    )


async def _patch_validators_and_run(
    db: AsyncSession,
    phases: tuple[Phase, ...],
    *,
    allow_empty: bool = False,
):
    """Patch the loader and validators for deterministic test input."""
    with (
        patch(
            "learn_to_cloud_shared.content_sync.get_all_phases_from_yaml",
            return_value=phases,
        ),
        patch(
            "learn_to_cloud_shared.content_sync.validate_content",
            return_value=[],
        ),
        patch(
            "learn_to_cloud_shared.content_sync.clear_cache",
            return_value=None,
        ),
    ):
        return await sync_curriculum_to_db(db, allow_empty=allow_empty)


async def test_first_sync_inserts_all_rows(
    db_session: AsyncSession, fresh_curriculum: tuple[Phase, ...]
) -> None:
    stats = await _patch_validators_and_run(db_session, fresh_curriculum)
    assert stats.phases_upserted == 1
    assert stats.topics_upserted == 1
    assert stats.steps_upserted == 1
    assert stats.objectives_upserted == 1
    assert stats.requirements_upserted == 1
    assert stats.rows_soft_deleted == 0

    phase = (await db_session.execute(select(CurriculumPhase))).scalar_one()
    assert phase.slug == "phase0"
    assert phase.deleted_at is None


async def test_second_sync_is_idempotent(
    db_session: AsyncSession, fresh_curriculum: tuple[Phase, ...]
) -> None:
    """Re-running with no changes must not bump updated_at."""
    await _patch_validators_and_run(db_session, fresh_curriculum)
    first = (await db_session.execute(select(CurriculumPhase))).scalar_one()
    first_updated_at: datetime = first.updated_at

    # Detach and re-run; the second sync should not touch the row.
    db_session.expire_all()
    await _patch_validators_and_run(db_session, fresh_curriculum)

    second = (await db_session.execute(select(CurriculumPhase))).scalar_one()
    assert second.updated_at == first_updated_at


async def test_changed_content_bumps_updated_at(
    db_session: AsyncSession, fresh_curriculum: tuple[Phase, ...]
) -> None:
    await _patch_validators_and_run(db_session, fresh_curriculum)
    first = (await db_session.execute(select(CurriculumPhase))).scalar_one()
    first_updated_at: datetime = first.updated_at

    # Change the phase name; re-run sync.
    db_session.expire_all()
    updated_phase = fresh_curriculum[0].model_copy(update={"name": "New Name"})
    await _patch_validators_and_run(db_session, (updated_phase,))

    # Expire again so the second read fetches the post-update row from
    # the DB rather than the ORM identity map.
    db_session.expire_all()
    second = (await db_session.execute(select(CurriculumPhase))).scalar_one()
    assert second.name == "New Name"
    assert second.updated_at > first_updated_at


async def test_absent_entity_is_soft_deleted(
    db_session: AsyncSession, fresh_curriculum: tuple[Phase, ...]
) -> None:
    await _patch_validators_and_run(db_session, fresh_curriculum)

    # Remove the requirement from YAML and re-sync.
    db_session.expire_all()
    topic = fresh_curriculum[0].topics[0]
    phase_no_req = _make_phase(topic=topic)
    stats = await _patch_validators_and_run(db_session, (phase_no_req,))

    db_session.expire_all()
    assert stats.rows_soft_deleted == 1
    req = (await db_session.execute(select(CurriculumRequirement))).scalar_one()
    assert req.deleted_at is not None


async def test_revived_entity_clears_deleted_at(
    db_session: AsyncSession, fresh_curriculum: tuple[Phase, ...]
) -> None:
    await _patch_validators_and_run(db_session, fresh_curriculum)

    # First, soft-delete by syncing without the requirement.
    db_session.expire_all()
    topic = fresh_curriculum[0].topics[0]
    phase_no_req = _make_phase(topic=topic)
    await _patch_validators_and_run(db_session, (phase_no_req,))
    db_session.expire_all()
    req = (await db_session.execute(select(CurriculumRequirement))).scalar_one()
    assert req.deleted_at is not None

    # Now re-add the requirement (same UUID) and sync again -- should revive.
    db_session.expire_all()
    await _patch_validators_and_run(db_session, fresh_curriculum)
    db_session.expire_all()
    req = (await db_session.execute(select(CurriculumRequirement))).scalar_one()
    assert req.deleted_at is None


async def test_empty_yaml_fails_closed(db_session: AsyncSession) -> None:
    with pytest.raises(ContentSyncError, match="No phases loaded"):
        await _patch_validators_and_run(db_session, ())


async def test_empty_yaml_with_allow_empty_succeeds(
    db_session: AsyncSession,
) -> None:
    stats = await _patch_validators_and_run(db_session, (), allow_empty=True)
    assert stats.phases_upserted == 0


async def test_submission_type_change_is_refused(
    db_session: AsyncSession, fresh_curriculum: tuple[Phase, ...]
) -> None:
    await _patch_validators_and_run(db_session, fresh_curriculum)

    # Build the same requirement with a different submission_type but the same UUID.
    db_session.expire_all()
    topic = fresh_curriculum[0].topics[0]
    req_uuid = "00000000-0000-0000-0000-000000000003"
    different_type_req = HandsOnRequirementAdapter.validate_python(
        {
            "uuid": req_uuid,
            "slug": "github-profile",
            "submission_type": "repo_fork",
            "name": "Requirement github-profile",
            "description": "Test requirement",
            "type_config": {"required_repo": "owner/repo"},
        }
    )
    bad_phase = Phase(
        uuid=UUID("00000000-0000-0000-0000-000000000001"),
        slug="phase0",
        name="Phase0",
        description="...",
        short_description="...",
        order=0,
        topic_slugs=[topic.slug],
        topics=[topic],
        hands_on_verification=PhaseHandsOnVerificationOverview(
            requirement_slugs=["github-profile"],
            requirements=[different_type_req],
        ),
    )

    with pytest.raises(ContentSyncError, match="submission_type"):
        await _patch_validators_and_run(db_session, (bad_phase,))


async def test_natural_key_collision_is_refused(
    db_session: AsyncSession, fresh_curriculum: tuple[Phase, ...]
) -> None:
    """Different UUID with the same active slug must fail loudly."""
    await _patch_validators_and_run(db_session, fresh_curriculum)

    # Build a NEW phase with same slug but different UUID.
    db_session.expire_all()
    collision_phase = _make_phase(
        uuid_str=str(uuid4()),  # different UUID
        slug="phase0",  # same active slug
    )

    with pytest.raises(ContentSyncError, match="immutable"):
        await _patch_validators_and_run(db_session, (collision_phase,))


async def test_validation_failure_blocks_sync(
    db_session: AsyncSession, fresh_curriculum: tuple[Phase, ...]
) -> None:
    """If validate_content returns errors, sync aborts before any writes."""
    with (
        patch(
            "learn_to_cloud_shared.content_sync.get_all_phases_from_yaml",
            return_value=fresh_curriculum,
        ),
        patch(
            "learn_to_cloud_shared.content_sync.validate_content",
            return_value=["something broke"],
        ),
        patch(
            "learn_to_cloud_shared.content_sync.clear_cache",
            return_value=None,
        ),
    ):
        with pytest.raises(ContentSyncError, match="validation failed"):
            await sync_curriculum_to_db(db_session)

    # Nothing should have been written.
    rows = (await db_session.execute(select(CurriculumPhase))).scalars().all()
    assert rows == []
