"""Integration tests for content_db_loader (issue #464 / Phase C).

PR 1 verifies that the DB loader returns the same Pydantic shape as
the YAML loader for the seeded curriculum content. PR 2 will swap the
public ``content_service`` API to delegate to the DB loader; until then
both coexist.
"""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from learn_to_cloud_shared.content_db_loader import (
    load_all_phases_from_db,
    load_phase_by_slug_from_db,
    load_topic_by_slugs_from_db,
    load_topic_by_uuid_from_db,
)
from learn_to_cloud_shared.content_sync import sync_curriculum_to_db
from learn_to_cloud_shared.content_yaml_loader import (
    clear_cache,
)
from learn_to_cloud_shared.content_yaml_loader import (
    get_all_phases_from_yaml as get_all_phases,
)
from learn_to_cloud_shared.models import (
    CurriculumPhase,
    CurriculumRequirement,
    CurriculumStep,
    CurriculumTopic,
)
from learn_to_cloud_shared.schemas import (
    RepoForkRequirement,
)

pytestmark = pytest.mark.integration


async def _seed_with_real_content(db: AsyncSession) -> None:
    """Run the real sync against the authored YAML content."""
    clear_cache()
    await sync_curriculum_to_db(db)


# ---------------------------------------------------------------------------
# Whole-tree parity: DB loader output == YAML loader output
# ---------------------------------------------------------------------------


async def test_db_loader_matches_yaml_loader_for_authored_content(
    db_session: AsyncSession,
) -> None:
    """The DB loader returns the same shape as the YAML loader.

    Runs the real ``sync_curriculum_to_db`` against the authored YAML
    (the same content the migration image syncs), then compares
    ``load_all_phases_from_db`` output against ``get_all_phases``.

    Uses ``model_dump(mode='json')`` so equality failures produce a
    readable diff instead of opaque Pydantic instance comparisons.
    """
    await _seed_with_real_content(db_session)

    clear_cache()
    yaml_phases = get_all_phases()
    db_phases = await load_all_phases_from_db(db_session)

    yaml_dump = [p.model_dump(mode="json") for p in yaml_phases]
    db_dump = [p.model_dump(mode="json") for p in db_phases]

    assert len(db_dump) == len(yaml_dump), (
        f"DB returned {len(db_dump)} phases vs YAML's {len(yaml_dump)}"
    )

    for yaml_phase, db_phase in zip(yaml_dump, db_dump, strict=True):
        assert db_phase == yaml_phase


async def test_db_loader_returns_phases_in_order(
    db_session: AsyncSession,
) -> None:
    await _seed_with_real_content(db_session)
    phases = await load_all_phases_from_db(db_session)
    orders = [p.order for p in phases]
    assert orders == sorted(orders), f"phases not ordered: {orders}"


async def test_db_loader_returns_steps_in_order_within_topic(
    db_session: AsyncSession,
) -> None:
    await _seed_with_real_content(db_session)
    phases = await load_all_phases_from_db(db_session)
    for phase in phases:
        for topic in phase.topics:
            orders = [s.order for s in topic.learning_steps]
            assert orders == sorted(orders), (
                f"{phase.slug}/{topic.slug}: step orders {orders}"
            )


async def test_db_loader_returns_requirements_in_order_within_phase(
    db_session: AsyncSession,
) -> None:
    """Slug-list order from _phase.yaml must round-trip through DB."""
    await _seed_with_real_content(db_session)
    db_phases = await load_all_phases_from_db(db_session)
    clear_cache()
    yaml_phases = get_all_phases()
    yaml_by_slug = {p.slug: p for p in yaml_phases}
    for db_phase in db_phases:
        yaml_phase = yaml_by_slug[db_phase.slug]
        db_req_slugs = [
            r.slug
            for r in (
                db_phase.hands_on_verification.requirements
                if db_phase.hands_on_verification
                else []
            )
        ]
        yaml_req_slugs = [
            r.slug
            for r in (
                yaml_phase.hands_on_verification.requirements
                if yaml_phase.hands_on_verification
                else []
            )
        ]
        assert db_req_slugs == yaml_req_slugs, (
            f"{db_phase.slug}: DB requirement order {db_req_slugs} "
            f"differs from YAML {yaml_req_slugs}"
        )


# ---------------------------------------------------------------------------
# Lookup helpers
# ---------------------------------------------------------------------------


async def test_load_phase_by_slug_returns_known_phase(
    db_session: AsyncSession,
) -> None:
    await _seed_with_real_content(db_session)
    phase = await load_phase_by_slug_from_db(db_session, "phase0")
    assert phase is not None
    assert phase.slug == "phase0"


async def test_load_phase_by_slug_returns_none_for_unknown(
    db_session: AsyncSession,
) -> None:
    await _seed_with_real_content(db_session)
    assert await load_phase_by_slug_from_db(db_session, "phase999") is None


async def test_load_topic_by_id_returns_known_topic(
    db_session: AsyncSession,
) -> None:
    await _seed_with_real_content(db_session)
    clear_cache()
    yaml_phases = get_all_phases()
    sample_topic = yaml_phases[0].topics[0]
    topic = await load_topic_by_uuid_from_db(db_session, sample_topic.uuid)
    assert topic is not None
    assert topic.uuid == sample_topic.uuid


async def test_load_topic_by_id_returns_none_for_unknown(
    db_session: AsyncSession,
) -> None:
    from uuid import uuid4

    await _seed_with_real_content(db_session)
    assert await load_topic_by_uuid_from_db(db_session, uuid4()) is None


async def test_load_topic_by_slugs_returns_known_topic(
    db_session: AsyncSession,
) -> None:
    await _seed_with_real_content(db_session)
    topic = await load_topic_by_slugs_from_db(
        db_session, "phase4", "monitoring-foundations-for-apps-and-vms"
    )
    assert topic is not None
    assert topic.slug == "monitoring-foundations-for-apps-and-vms"


async def test_load_topic_by_slugs_returns_none_when_phase_missing(
    db_session: AsyncSession,
) -> None:
    await _seed_with_real_content(db_session)
    assert await load_topic_by_slugs_from_db(db_session, "phase999", "anything") is None


# ---------------------------------------------------------------------------
# Soft-delete visibility
# ---------------------------------------------------------------------------


async def test_soft_deleted_phase_is_excluded(
    db_session: AsyncSession,
) -> None:
    await _seed_with_real_content(db_session)
    # Mark phase0 as soft-deleted in the DB; the loader must skip it.
    p0 = (
        await db_session.execute(
            select(CurriculumPhase).where(CurriculumPhase.slug == "phase0")
        )
    ).scalar_one()
    p0.deleted_at = datetime.now(UTC)
    await db_session.flush()
    db_session.expire_all()

    phases = await load_all_phases_from_db(db_session)
    assert all(p.slug != "phase0" for p in phases)


async def test_soft_deleted_topic_is_excluded(
    db_session: AsyncSession,
) -> None:
    await _seed_with_real_content(db_session)
    # Pick a real topic and soft-delete it.
    topic = (
        await db_session.execute(
            select(CurriculumTopic).where(CurriculumTopic.slug == "devops")
        )
    ).scalar_one()
    target_phase_uuid = topic.phase_uuid
    topic.deleted_at = datetime.now(UTC)
    await db_session.flush()
    db_session.expire_all()

    phases = await load_all_phases_from_db(db_session)
    phase = next(p for p in phases if p.uuid == target_phase_uuid)
    assert all(t.slug != "devops" for t in phase.topics)


async def test_soft_deleted_step_is_excluded(
    db_session: AsyncSession,
) -> None:
    await _seed_with_real_content(db_session)
    step = (
        await db_session.execute(
            select(CurriculumStep).where(CurriculumStep.deleted_at.is_(None)).limit(1)
        )
    ).scalar_one()
    target_topic_uuid = step.topic_uuid
    target_step_uuid = step.uuid
    step.deleted_at = datetime.now(UTC)
    await db_session.flush()
    db_session.expire_all()

    phases = await load_all_phases_from_db(db_session)
    for phase in phases:
        for topic in phase.topics:
            if topic.uuid == target_topic_uuid:
                assert all(s.uuid != target_step_uuid for s in topic.learning_steps)


async def test_soft_deleted_requirement_is_excluded(
    db_session: AsyncSession,
) -> None:
    await _seed_with_real_content(db_session)
    req = (
        await db_session.execute(
            select(CurriculumRequirement)
            .where(CurriculumRequirement.deleted_at.is_(None))
            .limit(1)
        )
    ).scalar_one()
    target_phase_uuid = req.phase_uuid
    target_req_uuid = req.uuid
    req.deleted_at = datetime.now(UTC)
    await db_session.flush()
    db_session.expire_all()

    phases = await load_all_phases_from_db(db_session)
    phase = next(p for p in phases if p.uuid == target_phase_uuid)
    if phase.hands_on_verification:
        assert all(
            r.uuid != target_req_uuid for r in phase.hands_on_verification.requirements
        )


# ---------------------------------------------------------------------------
# Requirement rehydration via discriminated union
# ---------------------------------------------------------------------------


async def test_requirement_rehydrates_to_correct_subclass(
    db_session: AsyncSession,
) -> None:
    """A 'repo_fork' DB row must round-trip to a RepoForkRequirement."""
    # Insert a synthetic phase + repo_fork requirement.
    now = datetime.now(UTC)
    phase = CurriculumPhase(
        uuid=uuid4(),
        slug="phase99",
        name="Phase 99",
        description="d",
        short_description="sd",
        order=99,
        deleted_at=None,
        created_at=now,
        updated_at=now,
    )
    db_session.add(phase)
    await db_session.flush()

    req_uuid = uuid4()
    req = CurriculumRequirement(
        uuid=req_uuid,
        phase_uuid=phase.uuid,
        slug="repo-fork-test",
        name="Test Fork",
        description="desc",
        submission_type="repo_fork",
        submission_value_kind="github_url",
        order=1,
        type_config={"required_repo": "owner/repo"},
        deleted_at=None,
        created_at=now,
        updated_at=now,
    )
    db_session.add(req)
    await db_session.flush()
    db_session.expire_all()

    phases = await load_all_phases_from_db(db_session)
    phase99 = next(p for p in phases if p.slug == "phase99")
    assert phase99.hands_on_verification is not None
    rebuilt = phase99.hands_on_verification.requirements[0]
    assert isinstance(rebuilt, RepoForkRequirement)
    assert rebuilt.required_repo == "owner/repo"


# ---------------------------------------------------------------------------
# Empty curriculum (defense in depth)
# ---------------------------------------------------------------------------


async def test_empty_db_returns_empty_tuple(
    db_session: AsyncSession,
) -> None:
    """No content should give an empty tuple, not an error."""
    phases = await load_all_phases_from_db(db_session)
    assert phases == ()
