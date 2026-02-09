"""Phase hands-on requirements sourced from content.

Requirements live in content/phases/**/_phase.yaml under
hands_on_verification.requirements. This module provides access helpers.
"""

from functools import lru_cache

from schemas import HandsOnRequirement


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


def get_requirement_by_id(requirement_id: str) -> HandsOnRequirement | None:
    """Get a specific requirement by its ID."""
    return _get_requirement_id_map().get(requirement_id)
