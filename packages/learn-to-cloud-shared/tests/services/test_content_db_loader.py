"""Integration tests for content_db_loader (issue #464 / Phase C).

PR 1 verifies that the DB loader returns the same Pydantic shape as
the YAML loader for the seeded curriculum content. PR 2 will swap the
public ``content_service`` API to delegate to the DB loader; until then
both coexist.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from uuid import uuid4

import pytest
from pydantic import ValidationError
from sqlalchemy import event, select
from sqlalchemy.engine import Engine
from sqlalchemy.ext.asyncio import AsyncSession

from learn_to_cloud_shared.content_db_loader import (
    load_all_phases_from_db,
    load_curriculum_overview_from_db,
    load_phase_by_slug_from_db,
    load_requirements_by_phase_order_from_db,
    load_topic_by_slugs_from_db,
    load_topic_by_uuid_from_db,
    load_topic_containing_step_from_db,
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
# Tolerant reader: unknown submission_type during a rolling deploy (#603)
# ---------------------------------------------------------------------------


async def _seed_phase_with_requirements(
    db_session: AsyncSession,
    *,
    order: int,
    requirements: list[CurriculumRequirement],
) -> CurriculumPhase:
    now = datetime.now(UTC)
    phase = CurriculumPhase(
        uuid=uuid4(),
        slug=f"phase{order}",
        name=f"Phase {order}",
        description="d",
        short_description="sd",
        order=order,
        deleted_at=None,
        created_at=now,
        updated_at=now,
    )
    db_session.add(phase)
    await db_session.flush()
    for i, req in enumerate(requirements, start=1):
        req.phase_uuid = phase.uuid
        req.order = i
        db_session.add(req)
    await db_session.flush()
    db_session.expire_all()
    return phase


def _make_requirement(
    *,
    slug: str,
    submission_type: str,
    submission_value_kind: str,
    type_config: dict,
) -> CurriculumRequirement:
    now = datetime.now(UTC)
    return CurriculumRequirement(
        uuid=uuid4(),
        phase_uuid=uuid4(),  # overwritten by _seed_phase_with_requirements
        slug=slug,
        name=slug,
        description="desc",
        submission_type=submission_type,
        submission_value_kind=submission_value_kind,
        order=0,
        type_config=type_config,
        deleted_at=None,
        created_at=now,
        updated_at=now,
    )


async def test_unknown_submission_type_is_skipped_not_raised(
    db_session: AsyncSession,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """A submission_type the code doesn't know (but the DB allows) is skipped.

    Reproduces the deploy-skew case: `ci_status` passes the requirements CHECK
    constraint (with `github_url`) but is not a tag in the discriminated union.
    The phase must still load and render only the known requirement.
    """
    known = _make_requirement(
        slug="known-fork",
        submission_type="repo_fork",
        submission_value_kind="github_url",
        type_config={"required_repo": "owner/repo"},
    )
    unknown = _make_requirement(
        slug="unknown-type",
        submission_type="ci_status",
        submission_value_kind="github_url",
        type_config={},
    )
    phase = await _seed_phase_with_requirements(
        db_session, order=97, requirements=[known, unknown]
    )

    with caplog.at_level("WARNING"):
        phases = await load_all_phases_from_db(db_session)

    loaded = next(p for p in phases if p.uuid == phase.uuid)
    assert loaded.hands_on_verification is not None
    slugs = [r.slug for r in loaded.hands_on_verification.requirements]
    assert slugs == ["known-fork"]
    assert any(
        "skipping_unknown_submission_type" in record.message
        for record in caplog.records
    )


async def test_unknown_submission_type_skipped_in_requirement_index_loader(
    db_session: AsyncSession,
) -> None:
    """The phase-order requirement loader also skips unknown types."""
    known = _make_requirement(
        slug="known-fork-2",
        submission_type="repo_fork",
        submission_value_kind="github_url",
        type_config={"required_repo": "owner/repo"},
    )
    unknown = _make_requirement(
        slug="unknown-type-2",
        submission_type="ci_status",
        submission_value_kind="github_url",
        type_config={},
    )
    await _seed_phase_with_requirements(
        db_session, order=96, requirements=[known, unknown]
    )

    by_order = await load_requirements_by_phase_order_from_db(db_session)
    loaded_slugs = [r.slug for r in by_order.get(96, [])]
    assert loaded_slugs == ["known-fork-2"]


async def test_malformed_config_for_known_type_still_raises(
    db_session: AsyncSession,
) -> None:
    """The gate only skips unknown types; a known type with bad config raises."""
    bad = _make_requirement(
        slug="bad-fork",
        submission_type="repo_fork",
        submission_value_kind="github_url",
        type_config={},  # missing required_repo
    )
    await _seed_phase_with_requirements(db_session, order=95, requirements=[bad])

    with pytest.raises(ValidationError):
        await load_all_phases_from_db(db_session)


# ---------------------------------------------------------------------------
# Empty curriculum (defense in depth)
# ---------------------------------------------------------------------------


async def test_empty_db_returns_empty_tuple(
    db_session: AsyncSession,
) -> None:
    """No content should give an empty tuple, not an error."""
    phases = await load_all_phases_from_db(db_session)
    assert phases == ()


# ---------------------------------------------------------------------------
# Query-count regressions for the narrower read shapes (curriculum
# read-shapes refactor). These guard against silently regressing back to
# full-tree loads for consumers that only need a small slice.
# ---------------------------------------------------------------------------


@contextmanager
def _count_queries() -> Iterator[list[str]]:
    """Count SQL statements executed against any engine during the block."""
    statements: list[str] = []

    def _before_cursor_execute(
        conn, cursor, statement, parameters, context, executemany
    ):
        statements.append(statement)

    event.listen(Engine, "before_cursor_execute", _before_cursor_execute)
    try:
        yield statements
    finally:
        event.remove(Engine, "before_cursor_execute", _before_cursor_execute)


async def test_curriculum_overview_is_two_queries(
    db_session: AsyncSession,
) -> None:
    """Shape B (browse-level overview) is 2 light queries, not 5 full-tree ones."""
    await _seed_with_real_content(db_session)

    with _count_queries() as statements:
        overview = await load_curriculum_overview_from_db(db_session)

    assert len(statements) == 2
    assert len(overview) > 0
    assert all(topic.name for phase in overview for topic in phase.topics)


async def test_phase_by_slug_does_not_load_other_phases(
    db_session: AsyncSession,
) -> None:
    """Loading one phase must not touch other phases' topics/steps."""
    await _seed_with_real_content(db_session)
    all_phases = await load_all_phases_from_db(db_session)
    other_phase = next(p for p in all_phases if p.slug != "phase0")

    phase0 = await load_phase_by_slug_from_db(db_session, "phase0")

    assert phase0 is not None
    assert all(
        t.uuid not in {t2.uuid for t2 in phase0.topics} for t in other_phase.topics
    )


async def test_topic_containing_step_is_scoped_not_full_tree(
    db_session: AsyncSession,
) -> None:
    """Shape E (single-step lookup) must not load the full curriculum tree.

    Resolves a step UUID to its parent topic via a handful of small,
    indexed queries -- never the whole 466-row curriculum.
    """
    await _seed_with_real_content(db_session)
    all_phases = await load_all_phases_from_db(db_session)
    target_step = next(
        step
        for phase in all_phases
        for topic in phase.topics
        for step in topic.learning_steps
    )

    with _count_queries() as statements:
        result = await load_topic_containing_step_from_db(db_session, target_step.uuid)

    assert result is not None
    topic, step = result
    assert step.uuid == target_step.uuid
    # Resolution query + topic row + steps + objectives = 4 small, indexed
    # queries -- independent of total curriculum size.
    assert len(statements) <= 4


async def test_requirement_index_is_two_queries_not_full_tree(
    db_session: AsyncSession,
) -> None:
    """Shape D (requirement index) only touches requirements + phases."""
    await _seed_with_real_content(db_session)

    with _count_queries() as statements:
        by_phase_order = await load_requirements_by_phase_order_from_db(db_session)

    assert len(statements) == 2
    assert sum(len(reqs) for reqs in by_phase_order.values()) > 0


async def test_requirement_index_skips_phase_query_when_mapping_provided(
    db_session: AsyncSession,
) -> None:
    """Passing a pre-loaded phase_order_by_uuid mapping saves one query."""
    await _seed_with_real_content(db_session)
    all_phases = await load_all_phases_from_db(db_session)
    phase_order_by_uuid = {p.uuid: p.order for p in all_phases}

    with _count_queries() as statements:
        await load_requirements_by_phase_order_from_db(
            db_session, phase_order_by_uuid=phase_order_by_uuid
        )

    assert len(statements) == 1
