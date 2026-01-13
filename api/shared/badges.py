"""Badge computation utilities for gamification.

Badges are computed on-the-fly from user progress data.
No separate database table is needed - badges are derived from:
- Question attempts (phase completion badges)
- User activities (streak badges)
"""

from dataclasses import dataclass
from datetime import date

# Phase badge definitions
PHASE_BADGES = {
    0: {
        "id": "phase_0_complete",
        "name": "Cloud Seedling",
        "description": "Completed Phase 0: Starting from Zero",
        "icon": "🌱",
        "phase_name": "IT Fundamentals & Cloud Overview",
    },
    1: {
        "id": "phase_1_complete",
        "name": "Terminal Ninja",
        "description": "Completed Phase 1: Linux & Bash",
        "icon": "🐧",
        "phase_name": "Command Line, Version Control & Infrastructure Basics",
    },
    2: {
        "id": "phase_2_complete",
        "name": "Code Crafter",
        "description": "Completed Phase 2: Programming & APIs",
        "icon": "🐍",
        "phase_name": "Python, FastAPI, Databases & AI Integration",
    },
    3: {
        "id": "phase_3_complete",
        "name": "Cloud Explorer",
        "description": "Completed Phase 3: Cloud Platform Fundamentals",
        "icon": "☁️",
        "phase_name": "VMs, Networking, Security & Deployment",
    },
    4: {
        "id": "phase_4_complete",
        "name": "DevOps Rocketeer",
        "description": "Completed Phase 4: DevOps & Containers",
        "icon": "🚀",
        "phase_name": "Docker, CI/CD, Kubernetes & Monitoring",
    },
    5: {
        "id": "phase_5_complete",
        "name": "Security Guardian",
        "description": "Completed Phase 5: Cloud Security",
        "icon": "🔐",
        "phase_name": "IAM, Data Protection & Threat Detection",
    },
}

# Streak badge definitions (ordered by requirement)
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

# Questions per phase (progress is now based on passed questions only)
# Phase 0: 12 questions (6 topics × 2 questions)
# Phase 1: 12 questions (6 topics × 2 questions)
# Phase 2: 14 questions (7 topics × 2 questions)
# Phase 3: 18 questions (9 topics × 2 questions)
# Phase 4: 12 questions (6 topics × 2 questions)
# Phase 5: 12 questions (6 topics × 2 questions)
# Total: 80 questions
PHASE_QUESTION_TOTALS = {
    0: 12,
    1: 12,
    2: 14,
    3: 18,
    4: 12,
    5: 12,
}


@dataclass
class Badge:
    """A badge that a user has earned."""

    id: str
    name: str
    description: str
    icon: str
    earned_at: date | None = None


def compute_phase_badges(
    phase_passed_counts: dict[int, int],
) -> list[Badge]:
    """Compute which phase badges a user has earned.

    Args:
        phase_passed_counts: Dict mapping phase_id -> passed questions count

    Returns:
        List of earned Badge objects
    """
    earned_badges = []

    for phase_id, badge_info in PHASE_BADGES.items():
        total_required = PHASE_QUESTION_TOTALS.get(phase_id, 0)
        passed = phase_passed_counts.get(phase_id, 0)

        if total_required > 0 and passed >= total_required:
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
    phase_passed_counts: dict[int, int],
    longest_streak: int,
) -> list[Badge]:
    """Compute all badges a user has earned.

    Args:
        phase_passed_counts: Dict mapping phase_id -> passed questions count
        longest_streak: User's longest streak (all-time)

    Returns:
        List of all earned Badge objects
    """
    badges = []
    badges.extend(compute_phase_badges(phase_passed_counts))
    badges.extend(compute_streak_badges(longest_streak))
    return badges


def get_all_available_badges() -> list[dict]:
    """Get all available badges (for displaying locked/unlocked states).

    Returns:
        List of badge info dicts with requirements
    """
    badges = []

    # Phase badges
    for phase_id, badge_info in PHASE_BADGES.items():
        total = PHASE_QUESTION_TOTALS.get(phase_id, 0)
        badges.append({
            **badge_info,
            "category": "phase",
            "requirement": f"Pass all {total} questions in Phase {phase_id}",
        })

    # Streak badges
    for badge_info in STREAK_BADGES:
        badges.append({
            **badge_info,
            "category": "streak",
            "requirement": f"Reach a {badge_info['required_streak']}-day streak",
        })

    return badges
