"""Tests for badge computation.

Source of truth:
- .github/skills/progression-system/SKILL.md (phase badges)
- .github/skills/streaks/SKILL.md (streak badges)

Key rules from SKILL.md:
- Phase badge awarded when phase reaches 100% completion
- 100% completion requires ALL: steps + questions + hands-on
- Streak badges use longest_streak (all-time), not current_streak
- Badges are permanent once earned
"""

from services.badges import (
    PHASE_BADGES,
    STREAK_BADGES,
    compute_all_badges,
    compute_phase_badges,
    compute_streak_badges,
    count_completed_phases,
    get_all_available_badges,
)
from services.progress import PHASE_REQUIREMENTS


class TestPhaseBadgeDefinitions:
    """Verify phase badges match SKILL.md source of truth."""

    def test_seven_phase_badges_exist(self):
        """SKILL.md: 7 phases (0-6), each has a badge."""
        assert len(PHASE_BADGES) == 7
        assert set(PHASE_BADGES.keys()) == {0, 1, 2, 3, 4, 5, 6}

    def test_phase_badge_names_match_skill_md(self):
        """SKILL.md badge names: Explorer, Practitioner, Builder, etc."""
        expected_names = {
            0: "Explorer",
            1: "Practitioner",
            2: "Builder",
            3: "Specialist",
            4: "Architect",
            5: "Master",
            6: "Legend",
        }
        for phase_id, expected_name in expected_names.items():
            assert PHASE_BADGES[phase_id]["name"] == expected_name

    def test_phase_badge_tiers_match_skill_md(self):
        """SKILL.md tiers: Bronze, Silver, Blue, Purple, Gold, Red, Rainbow."""
        # Tiers are represented by icons
        expected_icons = {
            0: "🥉",  # Bronze
            1: "🥈",  # Silver
            2: "🔵",  # Blue
            3: "🟣",  # Purple
            4: "🥇",  # Gold
            5: "🔴",  # Red
            6: "🌈",  # Rainbow
        }
        for phase_id, expected_icon in expected_icons.items():
            assert PHASE_BADGES[phase_id]["icon"] == expected_icon


class TestStreakBadgeDefinitions:
    """Verify streak badges match SKILL.md source of truth."""

    def test_three_streak_badges_exist(self):
        """SKILL.md: 3 streak badges at 7, 30, 100 days."""
        assert len(STREAK_BADGES) == 3

    def test_streak_badge_thresholds(self):
        """SKILL.md: Week Warrior (7), Monthly Master (30), Century Club (100)."""
        badge_by_streak = {b["required_streak"]: b for b in STREAK_BADGES}

        assert 7 in badge_by_streak
        assert badge_by_streak[7]["name"] == "Week Warrior"
        assert badge_by_streak[7]["icon"] == "🔥"

        assert 30 in badge_by_streak
        assert badge_by_streak[30]["name"] == "Monthly Master"
        assert badge_by_streak[30]["icon"] == "💪"

        assert 100 in badge_by_streak
        assert badge_by_streak[100]["name"] == "Century Club"
        assert badge_by_streak[100]["icon"] == "💯"


class TestPhaseCompletion:
    """Test phase completion badge logic.

    SKILL.md: A Phase is Complete when ALL three requirements are met:
    1. All Learning Steps completed
    2. All Knowledge Questions passed
    3. All Hands-on Requirements validated
    """

    def test_no_badges_with_no_progress(self):
        """No progress = no badges."""
        phase_counts = {}
        badges = compute_phase_badges(phase_counts)
        assert badges == []

    def test_no_badge_with_partial_steps(self):
        """SKILL.md: All steps must be completed."""
        # Phase 0 requires 15 steps, 12 questions
        phase_counts = {
            0: (10, 12, True),  # Only 10/15 steps
        }
        badges = compute_phase_badges(phase_counts)
        assert badges == []

    def test_no_badge_with_partial_questions(self):
        """SKILL.md: All questions must be passed."""
        phase_counts = {
            0: (15, 8, True),  # Only 8/12 questions
        }
        badges = compute_phase_badges(phase_counts)
        assert badges == []

    def test_no_badge_without_hands_on(self):
        """SKILL.md: All hands-on requirements must be validated."""
        phase_counts = {
            0: (15, 12, False),  # Hands-on not validated
        }
        badges = compute_phase_badges(phase_counts)
        assert badges == []

    def test_badge_awarded_at_exactly_required(self):
        """Badge awarded when exactly meeting requirements."""
        phase_counts = {
            0: (15, 12, True),  # Exactly 15 steps, 12 questions, hands-on done
        }
        badges = compute_phase_badges(phase_counts)

        assert len(badges) == 1
        assert badges[0].id == "phase_0_complete"
        assert badges[0].name == "Explorer"

    def test_badge_awarded_when_exceeding_required(self):
        """Badge awarded when exceeding requirements."""
        phase_counts = {
            0: (20, 15, True),  # More than required
        }
        badges = compute_phase_badges(phase_counts)

        assert len(badges) == 1
        assert badges[0].name == "Explorer"

    def test_multiple_phase_badges(self):
        """Multiple phases completed = multiple badges."""
        phase_counts = {
            0: (15, 12, True),
            1: (36, 12, True),
            2: (30, 12, True),
        }
        badges = compute_phase_badges(phase_counts)

        assert len(badges) == 3
        badge_names = {b.name for b in badges}
        assert badge_names == {"Explorer", "Practitioner", "Builder"}

    def test_all_phases_completed(self):
        """All 7 phases completed = 7 badges."""
        phase_counts = {
            0: (15, 12, True),
            1: (36, 12, True),
            2: (30, 12, True),
            3: (31, 8, True),
            4: (51, 18, True),
            5: (55, 12, True),
            6: (64, 12, True),
        }
        badges = compute_phase_badges(phase_counts)

        assert len(badges) == 7


class TestStreakBadgeComputation:
    """Test streak badge computation.

    SKILL.md: Badges use longest_streak (all-time), not current_streak.
    """

    def test_no_badges_with_zero_streak(self):
        """Zero streak = no badges."""
        badges = compute_streak_badges(0)
        assert badges == []

    def test_no_badges_below_7(self):
        """Streak of 6 = no badges."""
        badges = compute_streak_badges(6)
        assert badges == []

    def test_week_warrior_at_7(self):
        """SKILL.md: Week Warrior at 7 days."""
        badges = compute_streak_badges(7)

        assert len(badges) == 1
        assert badges[0].name == "Week Warrior"
        assert badges[0].icon == "🔥"

    def test_week_warrior_between_7_and_30(self):
        """Streak of 20 = only Week Warrior."""
        badges = compute_streak_badges(20)

        assert len(badges) == 1
        assert badges[0].name == "Week Warrior"

    def test_monthly_master_at_30(self):
        """SKILL.md: Monthly Master at 30 days (includes Week Warrior)."""
        badges = compute_streak_badges(30)

        assert len(badges) == 2
        badge_names = {b.name for b in badges}
        assert badge_names == {"Week Warrior", "Monthly Master"}

    def test_monthly_master_between_30_and_100(self):
        """Streak of 75 = Week Warrior + Monthly Master."""
        badges = compute_streak_badges(75)

        assert len(badges) == 2

    def test_century_club_at_100(self):
        """SKILL.md: Century Club at 100 days (includes all previous)."""
        badges = compute_streak_badges(100)

        assert len(badges) == 3
        badge_names = {b.name for b in badges}
        assert badge_names == {"Week Warrior", "Monthly Master", "Century Club"}

    def test_century_club_above_100(self):
        """Streak of 365 = all 3 badges."""
        badges = compute_streak_badges(365)

        assert len(badges) == 3


class TestCombinedBadges:
    """Test compute_all_badges combines phase and streak badges."""

    def test_empty_progress_zero_streak(self):
        """No progress and no streak = no badges."""
        badges = compute_all_badges({}, 0)
        assert badges == []

    def test_only_phase_badges(self):
        """Phase badges with no streak."""
        phase_counts = {0: (15, 12, True)}
        badges = compute_all_badges(phase_counts, 0)

        assert len(badges) == 1
        assert badges[0].name == "Explorer"

    def test_only_streak_badges(self):
        """Streak badges with no phase completion."""
        badges = compute_all_badges({}, 10)

        assert len(badges) == 1
        assert badges[0].name == "Week Warrior"

    def test_mixed_badges(self):
        """Both phase and streak badges."""
        phase_counts = {
            0: (15, 12, True),
            1: (36, 12, True),
        }
        badges = compute_all_badges(phase_counts, 35)

        assert len(badges) == 4  # 2 phase + 2 streak
        badge_names = {b.name for b in badges}
        assert "Explorer" in badge_names
        assert "Practitioner" in badge_names
        assert "Week Warrior" in badge_names
        assert "Monthly Master" in badge_names


class TestCountCompletedPhases:
    """Test count_completed_phases matches badge requirements."""

    def test_no_completed_phases(self):
        """No completion = 0 phases."""
        count = count_completed_phases({})
        assert count == 0

    def test_partial_completion_not_counted(self):
        """Partial phases don't count."""
        phase_counts = {
            0: (10, 12, True),  # Steps incomplete
            1: (36, 8, True),  # Questions incomplete
            2: (30, 12, False),  # Hands-on incomplete
        }
        count = count_completed_phases(phase_counts)
        assert count == 0

    def test_counts_match_badges(self):
        """Completed phase count should match badge count."""
        phase_counts = {
            0: (15, 12, True),
            1: (36, 12, True),
            2: (30, 12, True),
            3: (10, 4, False),  # Incomplete
        }
        count = count_completed_phases(phase_counts)
        badges = compute_phase_badges(phase_counts)

        assert count == 3
        assert len(badges) == 3


class TestPhaseRequirementsMatchSkillMd:
    """Verify PHASE_REQUIREMENTS matches SKILL.md table."""

    def test_phase_0_requirements(self):
        """SKILL.md: Phase 0 = 15 steps, 12 questions."""
        req = PHASE_REQUIREMENTS[0]
        assert req.steps == 15
        assert req.questions == 12

    def test_phase_1_requirements(self):
        """SKILL.md: Phase 1 = 36 steps, 12 questions."""
        req = PHASE_REQUIREMENTS[1]
        assert req.steps == 36
        assert req.questions == 12

    def test_phase_2_requirements(self):
        """SKILL.md: Phase 2 = 30 steps, 12 questions."""
        req = PHASE_REQUIREMENTS[2]
        assert req.steps == 30
        assert req.questions == 12

    def test_phase_3_requirements(self):
        """SKILL.md: Phase 3 = 31 steps, 8 questions."""
        req = PHASE_REQUIREMENTS[3]
        assert req.steps == 31
        assert req.questions == 8

    def test_phase_4_requirements(self):
        """SKILL.md: Phase 4 = 51 steps, 18 questions."""
        req = PHASE_REQUIREMENTS[4]
        assert req.steps == 51
        assert req.questions == 18

    def test_phase_5_requirements(self):
        """SKILL.md: Phase 5 = 55 steps, 12 questions."""
        req = PHASE_REQUIREMENTS[5]
        assert req.steps == 55
        assert req.questions == 12

    def test_phase_6_requirements(self):
        """SKILL.md: Phase 6 = 64 steps, 12 questions."""
        req = PHASE_REQUIREMENTS[6]
        assert req.steps == 64
        assert req.questions == 12


class TestGetAllAvailableBadges:
    """Test get_all_available_badges returns all badges for UI."""

    def test_returns_all_badges(self):
        """Should return all 10 badges (7 phase + 3 streak)."""
        badges = get_all_available_badges()
        assert len(badges) == 10

    def test_badges_have_category(self):
        """Each badge should have a category."""
        badges = get_all_available_badges()

        phase_badges = [b for b in badges if b["category"] == "phase"]
        streak_badges = [b for b in badges if b["category"] == "streak"]

        assert len(phase_badges) == 7
        assert len(streak_badges) == 3

    def test_badges_have_requirements(self):
        """Each badge should have a requirement string."""
        badges = get_all_available_badges()

        for badge in badges:
            assert "requirement" in badge
            assert len(badge["requirement"]) > 0
