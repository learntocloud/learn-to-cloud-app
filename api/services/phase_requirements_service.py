"""Phase hands-on requirements sourced from content.

Requirements live in content/phases/**/_phase.yaml under
hands_on_verification.requirements. This module provides access helpers.
"""

from __future__ import annotations

from functools import lru_cache
from typing import TYPE_CHECKING

from schemas import HandsOnRequirement

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession


@lru_cache(maxsize=1)
def _get_requirements_map() -> dict[int, list[HandsOnRequirement]]:
    from services.content_service import get_all_phases

    requirements_map: dict[int, list[HandsOnRequirement]] = {}
    for phase in get_all_phases():
        requirements = []
        if phase.hands_on_verification:
            requirements = list(phase.hands_on_verification.requirements)
        requirements_map[phase.id] = requirements
    return requirements_map


def get_requirements_for_phase(phase_id: int) -> list[HandsOnRequirement]:
    """Get all hands-on requirements for a specific phase."""
    return _get_requirements_map().get(phase_id, [])


@lru_cache(maxsize=1)
def _get_requirement_id_map() -> dict[str, HandsOnRequirement]:
    """Build flat lookup map of requirement_id → HandsOnRequirement."""
    return {req.id: req for reqs in _get_requirements_map().values() for req in reqs}


@lru_cache(maxsize=1)
def _get_requirement_phase_id_map() -> dict[str, int]:
    """Build lookup map of requirement_id → parent phase_id."""
    requirement_phase_map: dict[str, int] = {}
    for phase_id, requirements in _get_requirements_map().items():
        for requirement in requirements:
            requirement_phase_map[requirement.id] = phase_id
    return requirement_phase_map


def get_requirement_by_id(requirement_id: str) -> HandsOnRequirement | None:
    """Get a specific requirement by its ID."""
    return _get_requirement_id_map().get(requirement_id)


def get_phase_id_for_requirement(requirement_id: str) -> int | None:
    """Get parent phase_id for a requirement ID."""
    return _get_requirement_phase_id_map().get(requirement_id)


# Sequential gating: these phases require the prior phase's verification
# to be fully completed before their own verification can be submitted.
# Key = phase that is gated, Value = phase that must be completed first.
_PHASE_PREREQUISITES: dict[int, int] = {
    4: 3,
    5: 4,
    6: 5,
}


def get_prerequisite_phase(phase_id: int) -> int | None:
    """Return the phase that must be fully verified before this one, or None."""
    return _PHASE_PREREQUISITES.get(phase_id)


def get_requirement_ids_for_phase(phase_id: int) -> list[str]:
    """Return all requirement IDs for a phase."""
    return [req.id for req in get_requirements_for_phase(phase_id)]


async def is_phase_verification_locked(
    db: AsyncSession,
    user_id: int,
    phase_id: int,
) -> tuple[bool, int | None]:
    """Check if a phase's verification is locked behind an incomplete prerequisite.

    Returns:
        (is_locked, prerequisite_phase_id) — if locked, the phase that
        must be completed first; otherwise (False, None).
    """
    from repositories.submission_repository import SubmissionRepository

    prereq = get_prerequisite_phase(phase_id)
    if prereq is None:
        return False, None

    prereq_req_ids = get_requirement_ids_for_phase(prereq)
    if not prereq_req_ids:
        return False, None

    repo = SubmissionRepository(db)
    all_done = await repo.are_all_requirements_validated(user_id, prereq_req_ids)
    if all_done:
        return False, None

    return True, prereq
