"""Public curriculum read API (DB-backed).

After Phase C (issue #461), runtime reads in the API go through the DB
loader populated at deploy time by ``content_sync.py``. This module
provides the thin async wrappers callers use: pass an
``AsyncSession`` and get back the same Pydantic shape the YAML loader
used to return.

Per-request loads are uncached by design -- the curriculum is small
(~466 active rows, all indexed, 5 simple SELECTs) and a process-level
cache without invalidation creates a class of stale-data bugs we want
to avoid.

For the deploy-time YAML to DB sync and the strict cross-file
validators, use ``learn_to_cloud_shared.content_yaml_loader``.
"""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from learn_to_cloud_shared.content_db_loader import (
    load_all_phases_from_db,
    load_phase_by_slug_from_db,
)
from learn_to_cloud_shared.schemas import Phase


async def get_all_phases(db: AsyncSession) -> tuple[Phase, ...]:
    """Get all active phases in order, with nested topics and requirements."""
    return await load_all_phases_from_db(db)


async def get_phase_by_slug(db: AsyncSession, slug: str) -> Phase | None:
    """Get a phase by its slug (e.g. ``phase1``)."""
    return await load_phase_by_slug_from_db(db, slug)
