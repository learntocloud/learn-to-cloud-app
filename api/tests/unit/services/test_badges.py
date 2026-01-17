"""Unit tests for services/badges.py.

Tests badge computation logic following the progression system specification.

Total test cases: 35
- TestComputePhaseBadges: 10 tests
- TestComputeStreakBadges: 6 tests
- TestComputeAllBadges: 3 tests
- TestCountCompletedPhases: 4 tests
- TestGetAllAvailableBadges: 3 tests
"""

import pytest

from services.badges import (
    PHASE_BADGES,
    compute_all_badges,
    compute_phase_badges,
    compute_streak_badges,
    count_completed_phases,
    get_all_available_badges,
)
from services.progress import PHASE_REQUIREMENTS


class TestComputePhaseBadges:
    """Test compute_phase_badges function.

    Per spec: Phase badge awarded when ALL three requirements met:
    - All steps completed
    - All questions passed
    - All hands-on validated
    """

    def test_no_badges_with_zero_progress(self):
        """User with no progress earns no phase badges."""
        phase_completion = {
            0: (0, 0, False),
            1: (0, 0, False),
            2: (0, 0, False),
            3: (0, 0, False),
            4: (0, 0, False),
            5: (0, 0, False),
            6: (0, 0, False),
        }
        badges = compute_phase_badges(phase_completion)
        assert len(badges) == 0

    def test_phase_badge_awarded_when_complete(self):
        """Phase badge awarded when all requirements met."""
        req = PHASE_REQUIREMENTS[0]
        phase_completion = {0: (req.steps, req.questions, True)}
        badges = compute_phase_badges(phase_completion)

        assert len(badges) == 1
        assert badges[0].id == "phase_0_complete"
        assert badges[0].name == "Explorer"
        assert badges[0].icon == "🥉"

    def test_no_badge_with_partial_steps(self):
        """No badge when steps incomplete."""
        req = PHASE_REQUIREMENTS[0]
        phase_completion = {0: (10, req.questions, True)}
        badges = compute_phase_badges(phase_completion)
        assert len(badges) == 0

    def test_no_badge_with_partial_questions(self):
        """No badge when questions incomplete."""
        req = PHASE_REQUIREMENTS[0]
        phase_completion = {0: (req.steps, 6, True)}
        badges = compute_phase_badges(phase_completion)
        assert len(badges) == 0

    def test_no_badge_with_missing_hands_on(self):
        """No badge when hands-on not validated."""
        req = PHASE_REQUIREMENTS[0]
        phase_completion = {0: (req.steps, req.questions, False)}
        badges = compute_phase_badges(phase_completion)
        assert len(badges) == 0

    def test_multiple_phases_completed(self):
        """Multiple badges awarded for multiple completed phases."""
        req0 = PHASE_REQUIREMENTS[0]
        req1 = PHASE_REQUIREMENTS[1]
        phase_completion = {
            0: (req0.steps, req0.questions, True),
            1: (req1.steps, req1.questions, True),
        }
        badges = compute_phase_badges(phase_completion)

        assert len(badges) == 2
        badge_ids = {b.id for b in badges}
        assert "phase_0_complete" in badge_ids
        assert "phase_1_complete" in badge_ids

    def test_all_phases_completed(self):
        """All 7 phase badges awarded when all phases complete."""
        phase_completion = {}
        for phase_id, req in PHASE_REQUIREMENTS.items():
            phase_completion[phase_id] = (req.steps, req.questions, True)

        badges = compute_phase_badges(phase_completion)
        assert len(badges) == 7

        badge_ids = {b.id for b in badges}
        for phase_id in range(7):
            assert f"phase_{phase_id}_complete" in badge_ids

    def test_extra_progress_still_awards_badge(self):
        """Badge awarded even with extra progress."""
        req = PHASE_REQUIREMENTS[0]
        phase_completion = {0: (req.steps + 10, req.questions + 5, True)}
        badges = compute_phase_badges(phase_completion)

        assert len(badges) == 1
        assert badges[0].id == "phase_0_complete"

    @pytest.mark.parametrize("phase_id", [0, 1, 2, 3, 4, 5, 6])
    def test_badge_awarded_for_each_phase(self, phase_id):
        """Each phase awards its specific badge when complete."""
        req = PHASE_REQUIREMENTS[phase_id]
        phase_completion = {phase_id: (req.steps, req.questions, True)}
        badges = compute_phase_badges(phase_completion)

        assert len(badges) == 1
        assert badges[0].id == f"phase_{phase_id}_complete"
        assert badges[0].name == PHASE_BADGES[phase_id]["name"]
        assert badges[0].icon == PHASE_BADGES[phase_id]["icon"]

    def test_badge_not_awarded_for_missing_phase(self):
        """No badge awarded when phase data missing."""
        phase_completion = {}
        badges = compute_phase_badges(phase_completion)
        assert len(badges) == 0


class TestComputeStreakBadges:
    """Test compute_streak_badges function.

    Per spec:
    - Week Warrior: 7-day streak
    - Monthly Master: 30-day streak
    - Century Club: 100-day streak
    """

    def test_no_streak_badges_with_zero_streak(self):
        """No streak badges with 0-day streak."""
        badges = compute_streak_badges(0)
        assert len(badges) == 0

    def test_no_streak_badges_below_threshold(self):
        """No streak badges with 6-day streak (below threshold)."""
        badges = compute_streak_badges(6)
        assert len(badges) == 0

    def test_week_warrior_at_7_days(self):
        """Week Warrior badge awarded at 7 days."""
        badges = compute_streak_badges(7)

        assert len(badges) == 1
        assert badges[0].id == "streak_7"
        assert badges[0].name == "Week Warrior"
        assert badges[0].icon == "🔥"

    def test_two_badges_at_30_days(self):
        """Both Week Warrior and Monthly Master at 30 days."""
        badges = compute_streak_badges(30)

        assert len(badges) == 2
        badge_ids = {b.id for b in badges}
        assert "streak_7" in badge_ids
        assert "streak_30" in badge_ids

    def test_all_three_badges_at_100_days(self):
        """All three streak badges at 100 days."""
        badges = compute_streak_badges(100)

        assert len(badges) == 3
        badge_ids = {b.id for b in badges}
        assert "streak_7" in badge_ids
        assert "streak_30" in badge_ids
        assert "streak_100" in badge_ids

    @pytest.mark.parametrize(
        "streak,expected_badge_ids",
        [
            (0, []),
            (6, []),
            (7, ["streak_7"]),
            (29, ["streak_7"]),
            (30, ["streak_7", "streak_30"]),
            (99, ["streak_7", "streak_30"]),
            (100, ["streak_7", "streak_30", "streak_100"]),
            (365, ["streak_7", "streak_30", "streak_100"]),
        ],
    )
    def test_streak_thresholds(self, streak, expected_badge_ids):
        """Test all streak badge thresholds."""
        badges = compute_streak_badges(streak)
        badge_ids = {b.id for b in badges}
        assert badge_ids == set(expected_badge_ids)


class TestComputeAllBadges:
    """Test compute_all_badges function."""

    def test_new_user_has_no_badges(self):
        """New user with no progress and no streak has no badges."""
        phase_completion = {
            0: (0, 0, False),
            1: (0, 0, False),
            2: (0, 0, False),
            3: (0, 0, False),
            4: (0, 0, False),
            5: (0, 0, False),
            6: (0, 0, False),
        }
        badges = compute_all_badges(phase_completion, longest_streak=0)
        assert len(badges) == 0

    def test_phase_and_streak_badges_combined(self):
        """Phase and streak badges are combined."""
        req0 = PHASE_REQUIREMENTS[0]
        req1 = PHASE_REQUIREMENTS[1]
        phase_completion = {
            0: (req0.steps, req0.questions, True),
            1: (req1.steps, req1.questions, True),
        }
        badges = compute_all_badges(phase_completion, longest_streak=30)

        assert len(badges) == 4
        badge_ids = {b.id for b in badges}
        assert "phase_0_complete" in badge_ids
        assert "phase_1_complete" in badge_ids
        assert "streak_7" in badge_ids
        assert "streak_30" in badge_ids

    def test_max_badges_possible(self):
        """Maximum of 10 badges possible (7 phase + 3 streak)."""
        phase_completion = {}
        for phase_id, req in PHASE_REQUIREMENTS.items():
            phase_completion[phase_id] = (req.steps, req.questions, True)

        badges = compute_all_badges(phase_completion, longest_streak=100)
        assert len(badges) == 10


class TestCountCompletedPhases:
    """Test count_completed_phases function."""

    def test_zero_phases_completed(self):
        """Count is 0 when no phases complete."""
        phase_completion = {
            0: (0, 0, False),
            1: (0, 0, False),
        }
        count = count_completed_phases(phase_completion)
        assert count == 0

    def test_one_phase_completed(self):
        """Count is 1 when one phase complete."""
        req0 = PHASE_REQUIREMENTS[0]
        phase_completion = {
            0: (req0.steps, req0.questions, True),
            1: (0, 0, False),
        }
        count = count_completed_phases(phase_completion)
        assert count == 1

    def test_all_phases_completed(self):
        """Count is 7 when all phases complete."""
        phase_completion = {}
        for phase_id, req in PHASE_REQUIREMENTS.items():
            phase_completion[phase_id] = (req.steps, req.questions, True)

        count = count_completed_phases(phase_completion)
        assert count == 7

    def test_partial_completion_not_counted(self):
        """Partial completion doesn't increment count."""
        req0 = PHASE_REQUIREMENTS[0]
        req1 = PHASE_REQUIREMENTS[1]
        phase_completion = {
            0: (req0.steps, req0.questions, True),
            1: (req1.steps - 5, req1.questions, True),
        }
        count = count_completed_phases(phase_completion)
        assert count == 1


class TestGetAllAvailableBadges:
    """Test get_all_available_badges function."""

    def test_returns_all_badges(self):
        """Returns all 10 badges (7 phase + 3 streak)."""
        badges = get_all_available_badges()
        assert len(badges) == 10

    def test_phase_badges_have_requirements(self):
        """Phase badges include requirement strings."""
        badges = get_all_available_badges()
        phase_badges = [b for b in badges if b.get("category") == "phase"]

        assert len(phase_badges) == 7
        for badge in phase_badges:
            assert "requirement" in badge
            assert "Complete all" in badge["requirement"]

    def test_streak_badges_have_day_requirements(self):
        """Streak badges include day requirements."""
        badges = get_all_available_badges()
        streak_badges = [b for b in badges if b.get("category") == "streak"]

        assert len(streak_badges) == 3

        for badge in streak_badges:
            assert "requirement" in badge
            assert "day" in badge["requirement"]
            assert "streak" in badge["requirement"]
