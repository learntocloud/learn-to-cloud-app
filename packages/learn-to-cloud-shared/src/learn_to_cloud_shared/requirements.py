"""Phase hands-on requirements lookup helpers.

Backed by the DB curriculum (see ``content_service``). Each convenience
helper loads the lightweight requirement index (requirements + phases
only, not the full curriculum tree) and builds a ``RequirementIndex``;
hot paths that need several lookups should load the index once and
reuse it to avoid redundant queries.

Phases here are keyed by ``phase.order`` (the int 0..7), matching the
URL contract and the numeric phase id. Slugs (``"phase0"`` etc.) are
not used as the index key because callers (sequential gating, progress
aggregation) think in terms of ordinals.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING
from uuid import UUID

from learn_to_cloud_shared.content_service import get_requirements_by_phase_order
from learn_to_cloud_shared.repositories.submission_repository import (
    SubmissionRepository,
)
from learn_to_cloud_shared.schemas import HandsOnRequirement

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession


@dataclass(frozen=True)
class RequirementIndex:
    """Precomputed lookups over the loaded requirements.

    Build once per request via ``load_requirement_index`` and reuse for
    all requirement-shaped lookups in that request.
    """

    by_phase_order: dict[int, list[HandsOnRequirement]] = field(default_factory=dict)
    by_slug: dict[str, HandsOnRequirement] = field(default_factory=dict)
    phase_order_by_req_slug: dict[str, int] = field(default_factory=dict)

    @classmethod
    def from_requirements_by_phase_order(
        cls, requirements_by_phase_order: dict[int, list[HandsOnRequirement]]
    ) -> RequirementIndex:
        by_slug: dict[str, HandsOnRequirement] = {}
        phase_order_by_req_slug: dict[str, int] = {}
        for phase_order, reqs in requirements_by_phase_order.items():
            for req in reqs:
                by_slug[req.slug] = req
                phase_order_by_req_slug[req.slug] = phase_order
        return cls(
            by_phase_order=dict(requirements_by_phase_order),
            by_slug=by_slug,
            phase_order_by_req_slug=phase_order_by_req_slug,
        )

    def requirements_for_phase(self, phase_order: int) -> list[HandsOnRequirement]:
        return self.by_phase_order.get(phase_order, [])

    def requirement_slugs_for_phase(self, phase_order: int) -> list[str]:
        return [req.slug for req in self.requirements_for_phase(phase_order)]

    def requirement_uuids_for_phase(self, phase_order: int) -> list[UUID]:
        return [req.uuid for req in self.requirements_for_phase(phase_order)]


async def load_requirement_index(
    db: AsyncSession,
    *,
    phase_order_by_uuid: dict[UUID, int] | None = None,
) -> RequirementIndex:
    """Load the lightweight requirement index (requirements+phases only).

    Does not load the curriculum tree -- only the ``requirements`` and
    ``phases`` tables (~18 rows in production), since callers here only
    ever need UUIDs, slugs, and gating/validation metadata. Pass
    ``phase_order_by_uuid`` when the caller already has one to skip a
    redundant phases query.
    """
    return RequirementIndex.from_requirements_by_phase_order(
        await get_requirements_by_phase_order(
            db, phase_order_by_uuid=phase_order_by_uuid
        )
    )


async def get_requirement_by_slug(
    db: AsyncSession, requirement_slug: str
) -> HandsOnRequirement | None:
    """Get a specific requirement by its slug."""
    idx = await load_requirement_index(db)
    return idx.by_slug.get(requirement_slug)


# Sequential gating: these phases require the prior phase's verification
# to be fully completed before their own verification can be submitted.
# Key = phase that is gated, Value = phase that must be completed first.
# Phase keys are ``phase.order`` (int 0..7).
_PHASE_PREREQUISITES: dict[int, int] = {
    4: 3,
    5: 4,
    6: 5,
    7: 6,
}


def get_prerequisite_phase(phase_order: int) -> int | None:
    """Return the phase that must be fully verified before this one, or None.

    Pure lookup over a static dict; no DB or content access needed.
    """
    return _PHASE_PREREQUISITES.get(phase_order)


async def is_phase_verification_locked(
    db: AsyncSession,
    user_id: int,
    phase_order: int,
) -> tuple[bool, int | None]:
    """Check if a phase's verification is locked behind an incomplete prerequisite.

    Returns:
        (is_locked, prerequisite_phase_order). If locked, the second item
        is the phase order that must be completed first; otherwise
        (False, None).
    """
    prereq = get_prerequisite_phase(phase_order)
    if prereq is None:
        return False, None

    prereq_req_uuids = (await load_requirement_index(db)).requirement_uuids_for_phase(
        prereq
    )
    if not prereq_req_uuids:
        return False, None

    repo = SubmissionRepository(db)
    all_done = await repo.are_all_requirements_validated(user_id, prereq_req_uuids)
    if all_done:
        return False, None

    return True, prereq
