"""Badge computation utilities for gamification.

Badges are computed on-the-fly from user progress data.
No separate database table is needed - badges are derived from:
- Step completion + hands-on verification (phase completion badges)

CACHING:
- Badge computations are cached for 60 seconds per user+progress combination
- Cache key includes a hash of phase completion data for invalidation
"""

import logging
from functools import lru_cache

from core.cache import get_cached_badges, set_cached_badges
from schemas import BadgeCatalogItem, BadgeData
from services.content_service import get_all_phases
from services.progress_service import get_phase_requirements

logger = logging.getLogger(__name__)


@lru_cache(maxsize=1)
def _get_phase_badge_catalog() -> list[BadgeCatalogItem]:
    phase_badges: list[BadgeCatalogItem] = []

    phases = sorted(get_all_phases(), key=lambda p: p.order)
    for index, phase in enumerate(phases, start=1):
        if phase.badge:
            badge_id = f"phase_{phase.id}_complete"
            phase_badges.append(
                BadgeCatalogItem(
                    id=badge_id,
                    name=phase.badge.name,
                    description=phase.badge.description,
                    icon=phase.badge.icon,
                    num=f"#{index:03d}",
                    how_to=f"Complete Phase {phase.id}: {phase.name}",
                    phase_id=phase.id,
                    phase_name=phase.name,
                )
            )

    return phase_badges


def get_badge_catalog() -> tuple[list[BadgeCatalogItem], int]:
    """Get badge catalog derived from content."""
    phase_badges = _get_phase_badge_catalog()
    total_badges = len(phase_badges)
    return phase_badges, total_badges


def compute_phase_badges(
    phase_completion_counts: dict[int, tuple[int, bool]],
) -> list[BadgeData]:
    """Compute which phase badges a user has earned.

    A phase badge is earned when ALL of the following are true:
    - All steps in the phase are completed
    - All hands-on requirements are validated (if any exist)

    Args:
        phase_completion_counts: Dict mapping phase_id ->
            (completed_steps, hands_on_validated)

    Returns:
        List of earned BadgeData objects
    """
    earned_badges = []

    phase_badges = _get_phase_badge_catalog()

    for badge_info in phase_badges:
        if badge_info.phase_id is None:
            continue
        phase_id = badge_info.phase_id
        requirements = get_phase_requirements(phase_id)
        if not requirements:
            continue

        completed_steps, hands_on_validated = phase_completion_counts.get(
            phase_id, (0, False)
        )

        if completed_steps >= requirements.steps and hands_on_validated:
            earned_badges.append(
                BadgeData(
                    id=badge_info.id,
                    name=badge_info.name,
                    description=badge_info.description,
                    icon=badge_info.icon,
                )
            )

    return earned_badges


def compute_all_badges(
    phase_completion_counts: dict[int, tuple[int, bool]],
    user_id: int | None = None,
) -> list[BadgeData]:
    """Compute all badges a user has earned.

    Args:
        phase_completion_counts: Dict mapping phase_id ->
            (completed_steps, hands_on_validated)
        user_id: Optional user ID for caching (if provided, results are cached)

    Returns:
        List of all earned BadgeData objects

    CACHING: If user_id is provided, results are cached for 60 seconds.
    """
    if user_id:
        progress_hash = hash(
            tuple(sorted(phase_completion_counts.items())),
        )
        cached = get_cached_badges(user_id, progress_hash)
        if cached is not None:
            return cached

    badges = compute_phase_badges(phase_completion_counts)

    if user_id:
        logger.info(
            "badges.computed",
            extra={"user_id": user_id, "earned": len(badges)},
        )
        set_cached_badges(user_id, progress_hash, badges)

    return badges
