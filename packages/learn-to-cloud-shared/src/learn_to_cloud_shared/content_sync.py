"""Deploy-time sync from YAML curriculum to DB tables (issue #463).

Reads the packaged curriculum YAML, runs the strict cross-file
validators, and upserts every curriculum entity into its corresponding
DB table. Entities no longer present in YAML are soft-deleted; entities
that reappear (same UUID) have their ``deleted_at`` cleared. Idempotent
re-runs leave ``updated_at`` untouched unless something actually
changed.

This module does NOT load on app startup. It's intended to run once
per deploy via ``python -m learn_to_cloud_shared.cli.sync_curriculum``
in the Container Apps migration job, after ``alembic upgrade head``.

Design decisions (#461):
- **Strict load**: bypasses the tolerant ``get_all_phases`` to avoid
  silently soft-deleting valid content because of one bad file.
- **Fail closed**: empty curriculum aborts the sync instead of wiping
  every row. Override with ``allow_empty=True`` for tests.
- **Natural-key collision detection**: a new UUID with the same
  ``(phase_uuid, slug)`` as an existing active row raises rather than
  doing a silent delete+insert.
- **Revival**: a previously soft-deleted UUID reappearing in YAML
  clears ``deleted_at``.
- **Q3 enforcement**: changing ``submission_type`` on an existing
  requirement raises.
"""

from __future__ import annotations

import logging
from collections.abc import Iterable
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from typing import Any, Protocol
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from learn_to_cloud_shared.content_yaml_loader import (
    clear_cache,
    get_all_phases_from_yaml,
    validate_content,
)
from learn_to_cloud_shared.models import (
    CurriculumLearningObjective,
    CurriculumPhase,
    CurriculumRequirement,
    CurriculumStep,
    CurriculumTopic,
)
from learn_to_cloud_shared.schemas import Phase


class _CurriculumRowProtocol(Protocol):
    """Shape of every curriculum ORM row used by the sync helpers."""

    uuid: UUID
    deleted_at: datetime | None
    updated_at: datetime


logger = logging.getLogger(__name__)


class ContentSyncError(Exception):
    """Raised when sync cannot proceed safely."""


@dataclass(frozen=True, slots=True)
class SyncStats:
    """Counters reported after a sync run."""

    phases_upserted: int = 0
    topics_upserted: int = 0
    steps_upserted: int = 0
    objectives_upserted: int = 0
    requirements_upserted: int = 0
    rows_revived: int = 0
    rows_soft_deleted: int = 0


# Fields that the upsert compares to decide whether to bump
# ``updated_at``. ``uuid`` is the conflict target so it's not in this
# list; ``created_at`` is never updated.
_PHASE_UPDATE_FIELDS = (
    "legacy_id",
    "slug",
    "name",
    "description",
    "short_description",
    "order",
    "deleted_at",
    "updated_at",
)
_TOPIC_UPDATE_FIELDS = (
    "phase_uuid",
    "legacy_id",
    "slug",
    "name",
    "description",
    "order",
    "deleted_at",
    "updated_at",
)
_STEP_UPDATE_FIELDS = (
    "topic_uuid",
    "legacy_id",
    "order",
    "action",
    "title",
    "url",
    "description",
    "code",
    "extra_config",
    "deleted_at",
    "updated_at",
)
_OBJECTIVE_UPDATE_FIELDS = (
    "topic_uuid",
    "legacy_id",
    "text",
    "order",
    "deleted_at",
    "updated_at",
)
_REQUIREMENT_UPDATE_FIELDS = (
    "phase_uuid",
    "id",
    "name",
    "description",
    "submission_type",
    "order",
    "type_config",
    "deleted_at",
    "updated_at",
)


def _build_phase_row(phase: Phase, now: datetime) -> dict[str, Any]:
    return {
        "uuid": phase.uuid,
        "legacy_id": phase.id,
        "slug": phase.slug,
        "name": phase.name,
        "description": phase.description,
        "short_description": phase.short_description,
        "order": phase.order,
        "deleted_at": None,
        "created_at": now,
        "updated_at": now,
    }


def _build_topic_rows(phase: Phase, now: datetime) -> Iterable[dict[str, Any]]:
    for topic in phase.topics:
        yield {
            "uuid": topic.uuid,
            "phase_uuid": phase.uuid,
            "legacy_id": topic.id,
            "slug": topic.slug,
            "name": topic.name,
            "description": topic.description,
            "order": topic.order,
            "deleted_at": None,
            "created_at": now,
            "updated_at": now,
        }


def _build_step_rows(phase: Phase, now: datetime) -> Iterable[dict[str, Any]]:
    for topic in phase.topics:
        for step in topic.learning_steps:
            extra = step.model_dump(
                mode="json",
                exclude={
                    "uuid",
                    "id",
                    "order",
                    "action",
                    "title",
                    "url",
                    "description",
                    "code",
                },
                exclude_defaults=True,
            )
            yield {
                "uuid": step.uuid,
                "topic_uuid": topic.uuid,
                "legacy_id": step.id,
                "order": step.order,
                "action": step.action,
                "title": step.title,
                "url": step.url,
                "description": step.description,
                "code": step.code,
                "extra_config": extra or None,
                "deleted_at": None,
                "created_at": now,
                "updated_at": now,
            }


def _build_objective_rows(phase: Phase, now: datetime) -> Iterable[dict[str, Any]]:
    for topic in phase.topics:
        for objective in topic.learning_objectives:
            yield {
                "uuid": objective.uuid,
                "topic_uuid": topic.uuid,
                "legacy_id": objective.id,
                "text": objective.text,
                "order": objective.order,
                "deleted_at": None,
                "created_at": now,
                "updated_at": now,
            }


def _build_requirement_rows(phase: Phase, now: datetime) -> Iterable[dict[str, Any]]:
    if phase.hands_on_verification is None:
        return
    for idx, req in enumerate(phase.hands_on_verification.requirements):
        # type_config is a Pydantic submodel; dump as JSON-safe dict.
        type_config = req.type_config.model_dump(mode="json") if req.type_config else {}
        yield {
            "uuid": req.uuid,
            "phase_uuid": phase.uuid,
            "id": req.id,
            "name": req.name,
            "description": req.description,
            "submission_type": req.submission_type.value,
            # Position in _phase.yaml's requirement slug list = display order.
            # Mirrors the topic-order convention from #470: one source of truth.
            "order": idx + 1,
            "type_config": type_config,
            "deleted_at": None,
            "created_at": now,
            "updated_at": now,
        }


async def _upsert_rows(
    db: AsyncSession,
    model: Any,
    rows: list[dict[str, Any]],
    update_fields: tuple[str, ...],
    *,
    column_attr_overrides: dict[str, str] | None = None,
) -> None:
    """Insert each row or update on UUID conflict, only when changed.

    Uses ``ON CONFLICT (uuid) DO UPDATE ... WHERE excluded.X IS DISTINCT
    FROM existing.X`` so idempotent runs don't bump ``updated_at``.

    ``column_attr_overrides`` maps a column name (the key in ``rows``
    and the field name used by Postgres) to the Python attribute name
    on the ORM class when they differ (e.g. ``text`` column, ``text_``
    attribute to avoid shadowing the SQL builtin).
    """
    if not rows:
        return
    overrides = column_attr_overrides or {}

    def _col(field: str):
        return getattr(model, overrides.get(field, field))

    stmt = pg_insert(model).values(rows)
    update_dict = {f: getattr(stmt.excluded, f) for f in update_fields}
    # Build the IS DISTINCT FROM filter so unchanged rows are skipped.
    changed_predicate = None
    for f in update_fields:
        if f == "updated_at":
            continue
        clause = _col(f).is_distinct_from(getattr(stmt.excluded, f))
        changed_predicate = (
            clause if changed_predicate is None else changed_predicate | clause
        )
    stmt = stmt.on_conflict_do_update(
        index_elements=["uuid"],
        set_=update_dict,
        where=changed_predicate,
    )
    await db.execute(stmt)


async def _check_collisions_and_submission_type(
    db: AsyncSession,
    phases: tuple[Phase, ...],
) -> None:
    """Pre-flight checks that abort sync on data we can't safely apply.

    1. Natural-key collisions: an active row with the same
       ``(phase_uuid, slug)`` but a different UUID is treated as a YAML
       error -- UUIDs are supposed to be stable.
    2. submission_type changes on a requirement (matched by UUID) are
       refused per Q3 of #461.
    """
    yaml_topics_by_uuid: dict[UUID, tuple[Phase, Any]] = {}
    yaml_requirements_by_uuid: dict[UUID, tuple[Phase, Any]] = {}
    for p in phases:
        for t in p.topics:
            yaml_topics_by_uuid[t.uuid] = (p, t)
        if p.hands_on_verification:
            for r in p.hands_on_verification.requirements:
                yaml_requirements_by_uuid[r.uuid] = (p, r)

    # ---- Phase slug collisions ----
    db_phases = (
        (
            await db.execute(
                select(CurriculumPhase).where(CurriculumPhase.deleted_at.is_(None))
            )
        )
        .scalars()
        .all()
    )
    for db_phase in db_phases:
        for yaml_phase in phases:
            if db_phase.slug == yaml_phase.slug and db_phase.uuid != yaml_phase.uuid:
                raise ContentSyncError(
                    f"Phase slug '{yaml_phase.slug}' active in DB as "
                    f"uuid={db_phase.uuid} but YAML uses uuid={yaml_phase.uuid}. "
                    "UUIDs are immutable. Restore the original UUID in YAML "
                    "or soft-delete the DB row before changing identity."
                )

    # ---- Topic slug collisions within a phase ----
    db_topics = (
        (
            await db.execute(
                select(CurriculumTopic).where(CurriculumTopic.deleted_at.is_(None))
            )
        )
        .scalars()
        .all()
    )
    for db_topic in db_topics:
        for yaml_phase in phases:
            for yaml_topic in yaml_phase.topics:
                if (
                    db_topic.phase_uuid == yaml_phase.uuid
                    and db_topic.slug == yaml_topic.slug
                    and db_topic.uuid != yaml_topic.uuid
                ):
                    raise ContentSyncError(
                        f"Topic slug '{yaml_topic.slug}' in phase "
                        f"{yaml_phase.slug} active in DB as uuid={db_topic.uuid} "
                        f"but YAML uses uuid={yaml_topic.uuid}. UUIDs are "
                        "immutable."
                    )

    # ---- Requirement id collisions within a phase ----
    db_reqs = (
        (
            await db.execute(
                select(CurriculumRequirement).where(
                    CurriculumRequirement.deleted_at.is_(None)
                )
            )
        )
        .scalars()
        .all()
    )
    for db_req in db_reqs:
        for yaml_phase in phases:
            if not yaml_phase.hands_on_verification:
                continue
            for yaml_req in yaml_phase.hands_on_verification.requirements:
                if (
                    db_req.phase_uuid == yaml_phase.uuid
                    and db_req.id == yaml_req.id
                    and db_req.uuid != yaml_req.uuid
                ):
                    raise ContentSyncError(
                        f"Requirement id '{yaml_req.id}' in phase "
                        f"{yaml_phase.slug} active in DB as "
                        f"uuid={db_req.uuid} but YAML uses uuid="
                        f"{yaml_req.uuid}. UUIDs are immutable."
                    )

    # ---- submission_type change on same UUID ----
    for db_req in db_reqs:
        yaml_match = yaml_requirements_by_uuid.get(db_req.uuid)
        if yaml_match is None:
            continue  # absent from YAML; soft-delete handles it
        _, yaml_req = yaml_match
        if db_req.submission_type != yaml_req.submission_type.value:
            raise ContentSyncError(
                f"Requirement {db_req.id} (uuid={db_req.uuid}) is "
                f"changing submission_type from '{db_req.submission_type}' "
                f"to '{yaml_req.submission_type.value}'. This is destructive "
                "to existing submissions. Create a new requirement with a "
                "fresh UUID and soft-delete the old one instead."
            )


async def _soft_delete_absent(
    db: AsyncSession,
    model: Any,
    keep_uuids: set[UUID],
    now: datetime,
) -> int:
    """Soft-delete any active row whose UUID is not in ``keep_uuids``.

    ``model`` is typed as ``Any`` because static analysis can't bridge
    ``DeclarativeBase`` to the curriculum-specific columns
    (``uuid``, ``deleted_at``, ``updated_at``); see
    ``_CurriculumRowProtocol`` for the runtime contract.
    """
    # Fetch all active rows; we can't trivially express NOT IN on an
    # empty set in PostgreSQL ("NOT IN ()" is invalid syntax in some
    # client paths), so filter in Python after a fetch.
    rows: list[_CurriculumRowProtocol] = list(
        (await db.execute(select(model).where(model.deleted_at.is_(None))))
        .scalars()
        .all()
    )
    count = 0
    for row in rows:
        if row.uuid in keep_uuids:
            continue
        row.deleted_at = now
        row.updated_at = now
        count += 1
    return count


async def sync_curriculum_to_db(
    db: AsyncSession,
    *,
    allow_empty: bool = False,
) -> SyncStats:
    """Upsert the YAML curriculum into the DB tables.

    Runs cross-file validators first; aborts on any failure. Refuses to
    proceed if no phases load (a likely sign of a packaging or path bug)
    unless ``allow_empty=True`` is passed (useful for tests).

    Returns a ``SyncStats`` with counters. Errors raise
    ``ContentSyncError`` with a clear human message.
    """
    clear_cache()
    validation_errors = validate_content()
    if validation_errors:
        joined = "\n  - ".join(validation_errors)
        raise ContentSyncError(
            f"Curriculum validation failed; refusing to sync:\n  - {joined}"
        )

    phases = get_all_phases_from_yaml()
    if not phases and not allow_empty:
        raise ContentSyncError(
            "No phases loaded from YAML. Refusing to sync (would soft-delete "
            "every active row). Set allow_empty=True if this is intentional."
        )

    now = datetime.now(UTC)
    await _check_collisions_and_submission_type(db, phases)

    # Build all the row dicts up-front so we can count and so the upsert
    # gets a single list per table.
    phase_rows = [_build_phase_row(p, now) for p in phases]
    topic_rows = [r for p in phases for r in _build_topic_rows(p, now)]
    step_rows = [r for p in phases for r in _build_step_rows(p, now)]
    objective_rows = [r for p in phases for r in _build_objective_rows(p, now)]
    requirement_rows = [r for p in phases for r in _build_requirement_rows(p, now)]

    # Upsert in dependency order: phases -> topics/requirements -> steps/objectives.
    await _upsert_rows(db, CurriculumPhase, phase_rows, _PHASE_UPDATE_FIELDS)
    await _upsert_rows(db, CurriculumTopic, topic_rows, _TOPIC_UPDATE_FIELDS)
    await _upsert_rows(
        db, CurriculumRequirement, requirement_rows, _REQUIREMENT_UPDATE_FIELDS
    )
    await _upsert_rows(db, CurriculumStep, step_rows, _STEP_UPDATE_FIELDS)
    await _upsert_rows(
        db,
        CurriculumLearningObjective,
        objective_rows,
        _OBJECTIVE_UPDATE_FIELDS,
        column_attr_overrides={"text": "text_"},
    )

    # Soft-delete anything no longer in YAML. Order matters: child rows
    # first so the partial unique indexes don't briefly conflict.
    keep_phase = {r["uuid"] for r in phase_rows}
    keep_topic = {r["uuid"] for r in topic_rows}
    keep_step = {r["uuid"] for r in step_rows}
    keep_objective = {r["uuid"] for r in objective_rows}
    keep_requirement = {r["uuid"] for r in requirement_rows}

    deleted_total = 0
    deleted_total += await _soft_delete_absent(db, CurriculumStep, keep_step, now)
    deleted_total += await _soft_delete_absent(
        db, CurriculumLearningObjective, keep_objective, now
    )
    deleted_total += await _soft_delete_absent(
        db, CurriculumRequirement, keep_requirement, now
    )
    deleted_total += await _soft_delete_absent(db, CurriculumTopic, keep_topic, now)
    deleted_total += await _soft_delete_absent(db, CurriculumPhase, keep_phase, now)

    await db.flush()

    stats = SyncStats(
        phases_upserted=len(phase_rows),
        topics_upserted=len(topic_rows),
        steps_upserted=len(step_rows),
        objectives_upserted=len(objective_rows),
        requirements_upserted=len(requirement_rows),
        rows_soft_deleted=deleted_total,
    )
    logger.info("content_sync.complete", extra={"stats": asdict(stats)})
    return stats
