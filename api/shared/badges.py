"""Badge computation utilities for gamification.

Badges are computed on-the-fly from user progress data.
No separate database table is needed - badges are derived from:
- Step completion + Question attempts (phase completion badges)
- User activities (streak badges)
"""

from dataclasses import dataclass
from datetime import date

# Phase badge definitions (updated for 7-phase curriculum)
PHASE_BADGES = {
    0: {
        "id": "phase_0_complete",
        "name": "Cloud Seedling",
        "description": "Completed Phase 0: IT Fundamentals",
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
        "name": "AI Apprentice",
        "description": "Completed Phase 3: AI & Productivity",
        "icon": "🤖",
        "phase_name": "Prompt Engineering, GitHub Copilot & AI Tools",
    },
    4: {
        "id": "phase_4_complete",
        "name": "Cloud Explorer",
        "description": "Completed Phase 4: Cloud Deployment",
        "icon": "☁️",
        "phase_name": "VMs, Networking, Security & Deployment",
    },
    5: {
        "id": "phase_5_complete",
        "name": "DevOps Rocketeer",
        "description": "Completed Phase 5: DevOps & Containers",
        "icon": "🚀",
        "phase_name": "Docker, CI/CD, Kubernetes & Monitoring",
    },
    6: {
        "id": "phase_6_complete",
        "name": "Security Guardian",
        "description": "Completed Phase 6: Cloud Security",
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


@dataclass
class Badge:
    """A badge that a user has earned."""

    id: str
    name: str
    description: str
    icon: str
    earned_at: date | None = None


@dataclass
class PhaseRequirements:
    """Requirements to complete a phase (steps + questions)."""

    steps: int
    questions: int

    @property
    def total(self) -> int:
        return self.steps + self.questions


# Phase requirements: (steps, questions) per phase
# These are computed from the content files - update when content changes
# Last updated: 2026-01-14 from count_content.sh
PHASE_REQUIREMENTS: dict[int, PhaseRequirements] = {
    0: PhaseRequirements(steps=15, questions=12),  # 6 topics (IT Fundamentals)
    1: PhaseRequirements(steps=36, questions=12),  # 6 topics (CLI, Git, IaC)
    2: PhaseRequirements(steps=30, questions=12),  # 6 topics (Python, APIs)
    3: PhaseRequirements(steps=31, questions=8),   # 4 topics (AI phase)
    4: PhaseRequirements(steps=51, questions=18),  # 9 topics (Cloud deployment)
    5: PhaseRequirements(steps=55, questions=12),  # 6 topics (DevOps)
    6: PhaseRequirements(steps=64, questions=12),  # 6 topics (Security)
}


def compute_phase_badges(
    phase_completion_counts: dict[int, tuple[int, int, bool]],
) -> list[Badge]:
    """Compute which phase badges a user has earned.

    A phase badge is earned when ALL of the following are true:
    - All steps in the phase are completed
    - All questions in the phase are passed
    - All GitHub requirements are validated (if any exist)

    Args:
        phase_completion_counts: Dict mapping phase_id -> (completed_steps, passed_questions, github_validated)

    Returns:
        List of earned Badge objects
    """
    earned_badges = []

    for phase_id, badge_info in PHASE_BADGES.items():
        requirements = PHASE_REQUIREMENTS.get(phase_id)
        if not requirements:
            continue

        completed_steps, passed_questions, github_validated = phase_completion_counts.get(
            phase_id, (0, 0, True)  # Default github_validated to True (no requirements)
        )
        
        # Phase is complete when all steps AND all questions are done AND GitHub is validated
        if (
            completed_steps >= requirements.steps
            and passed_questions >= requirements.questions
            and github_validated
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
        phase_completion_counts: Dict mapping phase_id -> (completed_steps, passed_questions, github_validated)
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

    A phase is complete when all steps, questions, AND GitHub requirements are done.

    Args:
        phase_completion_counts: Dict mapping phase_id -> (completed_steps, passed_questions, github_validated)

    Returns:
        Number of completed phases
    """
    completed = 0
    for phase_id, requirements in PHASE_REQUIREMENTS.items():
        completed_steps, passed_questions, github_validated = phase_completion_counts.get(
            phase_id, (0, 0, True)
        )
        if (
            completed_steps >= requirements.steps
            and passed_questions >= requirements.questions
            and github_validated
        ):
            completed += 1
    return completed


def get_all_available_badges() -> list[dict]:
    """Get all available badges (for displaying locked/unlocked states).

    Returns:
        List of badge info dicts with requirements
    """
    badges = []

    # Phase badges
    for phase_id, badge_info in PHASE_BADGES.items():
        requirements = PHASE_REQUIREMENTS.get(phase_id)
        if requirements:
            badges.append({
                **badge_info,
                "category": "phase",
                "requirement": f"Complete all {requirements.steps} steps and {requirements.questions} questions in Phase {phase_id}",
            })

    # Streak badges
    for badge_info in STREAK_BADGES:
        badges.append({
            **badge_info,
            "category": "streak",
            "requirement": f"Reach a {badge_info['required_streak']}-day streak",
        })

    return badges
