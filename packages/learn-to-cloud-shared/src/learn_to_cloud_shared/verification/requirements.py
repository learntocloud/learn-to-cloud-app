"""Phase hands-on requirements lookup helpers.

Backed by the DB curriculum (see ``content_service``). Each convenience
helper loads the full phase tree and builds a ``RequirementIndex``;
hot paths that need several lookups should load phases once and call
``RequirementIndex.from_phases`` themselves to avoid redundant queries.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from learn_to_cloud_shared.content_service import get_all_phases
from learn_to_cloud_shared.repositories.submission_repository import (
    SubmissionRepository,
)
from learn_to_cloud_shared.schemas import HandsOnRequirement, Phase

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession


@dataclass(frozen=True)
class RequirementIndex:
    """Precomputed lookups over the loaded phases.

    Build once per request via ``from_phases`` and reuse for all
    requirement-shaped lookups in that request.
    """

    by_phase: dict[int, list[HandsOnRequirement]] = field(default_factory=dict)
    by_id: dict[str, HandsOnRequirement] = field(default_factory=dict)
    phase_id_by_req_id: dict[str, int] = field(default_factory=dict)

    @classmethod
    def from_phases(cls, phases: Sequence[Phase]) -> RequirementIndex:
        by_phase: dict[int, list[HandsOnRequirement]] = {}
        by_id: dict[str, HandsOnRequirement] = {}
        phase_id_by_req_id: dict[str, int] = {}
        for phase in phases:
            reqs: list[HandsOnRequirement] = []
            if phase.hands_on_verification:
                reqs = list(phase.hands_on_verification.requirements)
            by_phase[phase.id] = reqs
            for req in reqs:
                by_id[req.id] = req
                phase_id_by_req_id[req.id] = phase.id
        return cls(
            by_phase=by_phase,
            by_id=by_id,
            phase_id_by_req_id=phase_id_by_req_id,
        )

    def requirements_for_phase(self, phase_id: int) -> list[HandsOnRequirement]:
        return self.by_phase.get(phase_id, [])

    def requirement_ids_for_phase(self, phase_id: int) -> list[str]:
        return [req.id for req in self.requirements_for_phase(phase_id)]


async def load_requirement_index(db: AsyncSession) -> RequirementIndex:
    """Load all phases and build a ``RequirementIndex`` from them."""
    return RequirementIndex.from_phases(await get_all_phases(db))


async def get_requirements_for_phase(
    db: AsyncSession, phase_id: int
) -> list[HandsOnRequirement]:
    """Get all hands-on requirements for a specific phase."""
    idx = await load_requirement_index(db)
    return idx.requirements_for_phase(phase_id)


async def get_requirement_by_id(
    db: AsyncSession, requirement_id: str
) -> HandsOnRequirement | None:
    """Get a specific requirement by its ID."""
    idx = await load_requirement_index(db)
    return idx.by_id.get(requirement_id)


async def get_phase_id_for_requirement(
    db: AsyncSession, requirement_id: str
) -> int | None:
    """Get parent phase_id for a requirement ID."""
    idx = await load_requirement_index(db)
    return idx.phase_id_by_req_id.get(requirement_id)


async def get_requirement_ids_for_phase(db: AsyncSession, phase_id: int) -> list[str]:
    """Return all requirement IDs for a phase."""
    idx = await load_requirement_index(db)
    return idx.requirement_ids_for_phase(phase_id)


# Sequential gating: these phases require the prior phase's verification
# to be fully completed before their own verification can be submitted.
# Key = phase that is gated, Value = phase that must be completed first.
_PHASE_PREREQUISITES: dict[int, int] = {
    4: 3,
    5: 4,
    6: 5,
}


def get_prerequisite_phase(phase_id: int) -> int | None:
    """Return the phase that must be fully verified before this one, or None.

    Pure lookup over a static dict; no DB or content access needed.
    """
    return _PHASE_PREREQUISITES.get(phase_id)


async def is_phase_verification_locked(
    db: AsyncSession,
    user_id: int,
    phase_id: int,
) -> tuple[bool, int | None]:
    """Check if a phase's verification is locked behind an incomplete prerequisite.

    Returns:
        (is_locked, prerequisite_phase_id). If locked, the second item is
        the phase that must be completed first; otherwise (False, None).
    """
    prereq = get_prerequisite_phase(phase_id)
    if prereq is None:
        return False, None

    prereq_req_ids = await get_requirement_ids_for_phase(db, prereq)
    if not prereq_req_ids:
        return False, None

    repo = SubmissionRepository(db)
    all_done = await repo.are_all_requirements_validated(user_id, prereq_req_ids)
    if all_done:
        return False, None

    return True, prereq
