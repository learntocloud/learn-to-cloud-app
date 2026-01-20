"""Badge computation utilities for gamification.

Badges are computed on-the-fly from user progress data.
No separate database table is needed - badges are derived from:
- Step completion + Question attempts (phase completion badges)
- User activities (streak badges)

CACHING:
- Badge computations are cached for 60 seconds per user+progress combination
- Cache key includes a hash of phase completion data for invalidation
"""

from typing import TypedDict

from core.cache import get_cached_badges, set_cached_badges
from core.telemetry import add_custom_attribute
from schemas import BadgeData
from services.progress_service import get_phase_requirements

# Alias for backwards compatibility
Badge = BadgeData


class StreakBadgeInfo(TypedDict):
    """Streak badge configuration."""

    id: str
    name: str
    description: str
    icon: str
    required_streak: int


PHASE_BADGES = {
    0: {
        "id": "phase_0_complete",
        "name": "Explorer",
        "description": "Completed Phase 0",
        "icon": "🥉",
        "phase_name": "IT Fundamentals & Cloud Overview",
    },
    1: {
        "id": "phase_1_complete",
        "name": "Practitioner",
        "description": "Completed Phase 1",
        "icon": "🥈",
        "phase_name": "Linux, CLI & Version Control",
    },
    2: {
        "id": "phase_2_complete",
        "name": "Builder",
        "description": "Completed Phase 2",
        "icon": "🔵",
        "phase_name": "Programming & APIs",
    },
    3: {
        "id": "phase_3_complete",
        "name": "Specialist",
        "description": "Completed Phase 3",
        "icon": "🟣",
        "phase_name": "AI & Productivity",
    },
    4: {
        "id": "phase_4_complete",
        "name": "Architect",
        "description": "Completed Phase 4",
        "icon": "🥇",
        "phase_name": "Cloud Deployment",
    },
    5: {
        "id": "phase_5_complete",
        "name": "Master",
        "description": "Completed Phase 5",
        "icon": "🔴",
        "phase_name": "DevOps & Containers",
    },
    6: {
        "id": "phase_6_complete",
        "name": "Legend",
        "description": "Completed Phase 6",
        "icon": "🌈",
        "phase_name": "Cloud Security",
    },
}

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


def compute_phase_badges(
    phase_completion_counts: dict[int, tuple[int, int, bool]],
) -> list[Badge]:
    """Compute which phase badges a user has earned.

    A phase badge is earned when ALL of the following are true:
    - All steps in the phase are completed
    - All questions in the phase are passed
    - All hands-on requirements are validated (if any exist)

    Args:
        phase_completion_counts: Dict mapping phase_id ->
            (completed_steps, passed_questions, hands_on_validated)

    Returns:
        List of earned Badge objects
    """
    earned_badges = []

    for phase_id, badge_info in PHASE_BADGES.items():
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
                Badge(
                    id=badge_info["id"],
                    name=badge_info["name"],
                    description=badge_info["description"],
                    icon=badge_info["icon"],
                )
            )

    return earned_badges


def compute_streak_badges(longest_streak: int) -> list[Badge]:
    """Compute which streak badges a user has earned.

    Args:
        longest_streak: User's longest streak (all-time)

    Returns:
        List of earned Badge objects
    """
    earned_badges = []

    for badge_info in STREAK_BADGES:
        if longest_streak >= badge_info["required_streak"]:
            earned_badges.append(
                Badge(
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
) -> list[Badge]:
    """Compute all badges a user has earned.

    Args:
        phase_completion_counts: Dict mapping phase_id ->
            (completed_steps, passed_questions, hands_on_validated)
        longest_streak: User's longest streak (all-time)
        user_id: Optional user ID for caching (if provided, results are cached)

    Returns:
        List of all earned Badge objects

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
