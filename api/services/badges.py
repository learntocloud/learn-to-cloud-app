"""Badge computation utilities for gamification.

Badges are computed on-the-fly from user progress data.
No separate database table is needed - badges are derived from:
- Step completion + Question attempts (phase completion badges)
- User activities (streak badges)
"""

from dataclasses import dataclass
from datetime import date

from .progress import PHASE_REQUIREMENTS as _PROGRESS_REQUIREMENTS

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

STREAK_BADGES = [
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

@dataclass
class Badge:
    """A badge that a user has earned."""

    id: str
    name: str
    description: str
    icon: str
    earned_at: date | None = None

def compute_phase_badges(
    phase_completion_counts: dict[int, tuple[int, int, bool]],
) -> list[Badge]:
    """Compute which phase badges a user has earned.

    A phase badge is earned when ALL of the following are true:
    - All steps in the phase are completed
    - All questions in the phase are passed
    - All hands-on requirements are validated (if any exist)

    Args:
        phase_completion_counts: Dict mapping phase_id -> (completed_steps, passed_questions, hands_on_validated)

    Returns:
        List of earned Badge objects
    """
    earned_badges = []

    for phase_id, badge_info in PHASE_BADGES.items():
        requirements = _PROGRESS_REQUIREMENTS.get(phase_id)
        if not requirements:
            continue

        completed_steps, passed_questions, hands_on_validated = phase_completion_counts.get(
            phase_id, (0, 0, True)
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

def compute_streak_badges(
    longest_streak: int,
) -> list[Badge]:
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
) -> list[Badge]:
    """Compute all badges a user has earned.

    Args:
        phase_completion_counts: Dict mapping phase_id -> (completed_steps, passed_questions, hands_on_validated)
        longest_streak: User's longest streak (all-time)

    Returns:
        List of all earned Badge objects
    """
    badges = []
    badges.extend(compute_phase_badges(phase_completion_counts))
    badges.extend(compute_streak_badges(longest_streak))
    return badges

def count_completed_phases(
    phase_completion_counts: dict[int, tuple[int, int, bool]],
) -> int:
    """Count how many phases are fully completed.

    A phase is complete when all steps, questions, AND hands-on requirements are done.

    Args:
        phase_completion_counts: Dict mapping phase_id -> (completed_steps, passed_questions, hands_on_validated)

    Returns:
        Number of completed phases
    """
    completed = 0
    for phase_id, requirements in _PROGRESS_REQUIREMENTS.items():
        completed_steps, passed_questions, hands_on_validated = phase_completion_counts.get(
            phase_id, (0, 0, True)
        )
        if (
            completed_steps >= requirements.steps
            and passed_questions >= requirements.questions
            and hands_on_validated
        ):
            completed += 1
    return completed

def get_all_available_badges() -> list[dict]:
    """Get all available badges (for displaying locked/unlocked states).

    Returns:
        List of badge info dicts with requirements
    """
    badges = []

    for phase_id, badge_info in PHASE_BADGES.items():
        requirements = _PROGRESS_REQUIREMENTS.get(phase_id)
        if requirements:
            from services.hands_on_verification import get_requirements_for_phase

            hands_on_count = len(get_requirements_for_phase(phase_id))
            if hands_on_count:
                requirement_str = (
                    f"Complete all {requirements.steps} steps, {requirements.questions} questions, "
                    f"and {hands_on_count} hands-on requirements in Phase {phase_id}"
                )
            else:
                requirement_str = (
                    f"Complete all {requirements.steps} steps and {requirements.questions} questions in Phase {phase_id}"
                )
            badges.append({
                **badge_info,
                "category": "phase",
                "requirement": requirement_str,
            })

    for badge_info in STREAK_BADGES:
        badges.append({
            **badge_info,
            "category": "streak",
            "requirement": f"Reach a {badge_info['required_streak']}-day streak",
        })

    return badges
