"""Badge computation utilities for gamification.

Badges are computed on-the-fly from user progress data.
No separate database table is needed - badges are derived from:
- Step completion + Question attempts (phase completion badges)
- User activities (streak badges)

CACHING:
- Badge computations are cached for 60 seconds per user+progress combination
- Cache key includes a hash of phase completion data for invalidation
"""

from functools import lru_cache
from typing import TypedDict

from core.cache import get_cached_badges, set_cached_badges
from core.telemetry import add_custom_attribute
from schemas import BadgeCatalogItem, BadgeData, PhaseThemeData
from services.content_service import get_all_phases
from services.progress_service import get_phase_requirements


class StreakBadgeInfo(TypedDict):
    """Streak badge configuration."""

    id: str
    name: str
    description: str
    icon: str
    required_streak: int


STREAK_BADGES: list[StreakBadgeInfo] = [
    {
        "id": "streak_7",
        "name": "Week Warrior",
        "description": "Maintained a 7-day learning streak",
        "icon": "🔥",
        "required_streak": 7,
    },
    {
        "id": "streak_30",
        "name": "Monthly Master",
        "description": "Maintained a 30-day learning streak",
        "icon": "💪",
        "required_streak": 30,
    },
    {
        "id": "streak_100",
        "name": "Century Club",
        "description": "Maintained a 100-day learning streak",
        "icon": "💯",
        "required_streak": 100,
    },
]


@lru_cache(maxsize=1)
def _get_phase_badge_catalog() -> tuple[list[BadgeCatalogItem], list[PhaseThemeData]]:
    phase_badges: list[BadgeCatalogItem] = []
    phase_themes: list[PhaseThemeData] = []

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

        if phase.theme:
            phase_themes.append(
                PhaseThemeData(
                    phase_id=phase.id,
                    icon=phase.theme.icon,
                    bg_class=phase.theme.bg_class,
                    border_class=phase.theme.border_class,
                    text_class=phase.theme.text_class,
                )
            )

    return phase_badges, phase_themes


def get_badge_catalog() -> (
    tuple[list[BadgeCatalogItem], list[BadgeCatalogItem], int, list[PhaseThemeData]]
):
    """Get badge catalog and phase themes derived from content."""
    phase_badges, phase_themes = _get_phase_badge_catalog()
    streak_offset = len(phase_badges)
    streak_badges: list[BadgeCatalogItem] = []

    for index, badge_info in enumerate(STREAK_BADGES, start=1):
        streak_badges.append(
            BadgeCatalogItem(
                id=badge_info["id"],
                name=badge_info["name"],
                description=badge_info["description"],
                icon=badge_info["icon"],
                num=f"#{streak_offset + index:03d}",
                how_to=(
                    f"Maintain a {badge_info['required_streak']}-day learning streak"
                ),
            )
        )

    total_badges = len(phase_badges) + len(streak_badges)
    return phase_badges, streak_badges, total_badges, phase_themes


def compute_phase_badges(
    phase_completion_counts: dict[int, tuple[int, int, bool]],
) -> list[BadgeData]:
    """Compute which phase badges a user has earned.

    A phase badge is earned when ALL of the following are true:
    - All steps in the phase are completed
    - All questions in the phase are passed
    - All hands-on requirements are validated (if any exist)

    Args:
        phase_completion_counts: Dict mapping phase_id ->
            (completed_steps, passed_questions, hands_on_validated)

    Returns:
        List of earned BadgeData objects
    """
    earned_badges = []

    phase_badges, _ = _get_phase_badge_catalog()

    for badge_info in phase_badges:
        if badge_info.phase_id is None:
            continue
        phase_id = badge_info.phase_id
        requirements = get_phase_requirements(phase_id)
        if not requirements:
            continue

        completed_steps, passed_questions, hands_on_validated = (
            phase_completion_counts.get(phase_id, (0, 0, True))
        )

        if (
            completed_steps >= requirements.steps
            and passed_questions >= requirements.questions
            and hands_on_validated
        ):
            earned_badges.append(
                BadgeData(
                    id=badge_info.id,
                    name=badge_info.name,
                    description=badge_info.description,
                    icon=badge_info.icon,
                )
            )

    return earned_badges


def compute_streak_badges(longest_streak: int) -> list[BadgeData]:
    """Compute which streak badges a user has earned.

    Args:
        longest_streak: User's longest streak (all-time)

    Returns:
        List of earned BadgeData objects
    """
    earned_badges = []

    for badge_info in STREAK_BADGES:
        if longest_streak >= badge_info["required_streak"]:
            earned_badges.append(
                BadgeData(
                    id=badge_info["id"],
                    name=badge_info["name"],
                    description=badge_info["description"],
                    icon=badge_info["icon"],
                )
            )

    return earned_badges


def compute_all_badges(
    phase_completion_counts: dict[int, tuple[int, int, bool]],
    longest_streak: int,
    user_id: str | None = None,
) -> list[BadgeData]:
    """Compute all badges a user has earned.

    Args:
        phase_completion_counts: Dict mapping phase_id ->
            (completed_steps, passed_questions, hands_on_validated)
        longest_streak: User's longest streak (all-time)
        user_id: Optional user ID for caching (if provided, results are cached)

    Returns:
        List of all earned BadgeData objects

    CACHING: If user_id is provided, results are cached for 60 seconds.
    """
    if user_id:
        progress_hash = hash(
            (
                tuple(sorted(phase_completion_counts.items())),
                longest_streak,
            )
        )
        cached = get_cached_badges(user_id, progress_hash)
        if cached is not None:
            return cached

    badges = []
    badges.extend(compute_phase_badges(phase_completion_counts))
    badges.extend(compute_streak_badges(longest_streak))

    # Log metrics for badge awards (only on cache miss to avoid duplicate counts)
    if badges:
        phase_count = sum(1 for b in badges if b.id.startswith("phase_"))
        streak_count = sum(1 for b in badges if b.id.startswith("streak_"))
        if phase_count:
            add_custom_attribute("badges.phase_count", phase_count)
        if streak_count:
            add_custom_attribute("badges.streak_count", streak_count)

    if user_id:
        set_cached_badges(user_id, progress_hash, badges)

    return badges
