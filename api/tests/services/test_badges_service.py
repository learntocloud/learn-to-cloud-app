"""Tests for badges_service.

Tests badge computation logic - these are pure functions
that don't require database access.

Note: Phase requirements are loaded from content JSON files:
- Phase 0: 15 steps, 12 questions
- Phase 1: 36 steps, 12 questions
- Phase 2: 30 steps, 12 questions
"""

from services.badges_service import (
    compute_all_badges,
    compute_phase_badges,
    compute_streak_badges,
)


class TestComputePhaseBadges:
    """Tests for compute_phase_badges()."""

    def test_returns_empty_for_no_progress(self):
        """Should return no badges when no phases completed."""
        result = compute_phase_badges({})

        assert result == []

    def test_returns_badge_for_completed_phase(self):
        """Should return badge when all requirements met for a phase."""
        # Phase 0 requires 15 steps, 12 questions, hands-on validated
        phase_completion = {
            0: (15, 12, True),  # (steps, questions, hands_on_validated)
        }

        result = compute_phase_badges(phase_completion)

        assert len(result) == 1
        assert result[0].id == "phase_0_complete"
        assert result[0].name == "Explorer"
        assert result[0].icon == "🥉"

    def test_no_badge_when_steps_incomplete(self):
        """Should not award badge when steps not completed."""
        phase_completion = {
            0: (10, 12, True),  # Only 10 of 15 steps
        }

        result = compute_phase_badges(phase_completion)

        assert result == []

    def test_no_badge_when_questions_incomplete(self):
        """Should not award badge when questions not passed."""
        phase_completion = {
            0: (15, 5, True),  # Only 5 of 12 questions
        }

        result = compute_phase_badges(phase_completion)

        assert result == []

    def test_no_badge_when_hands_on_not_validated(self):
        """Should not award badge when hands-on not validated."""
        phase_completion = {
            0: (15, 12, False),  # Hands-on not validated
        }

        result = compute_phase_badges(phase_completion)

        assert result == []

    def test_multiple_phase_badges(self):
        """Should return multiple badges for multiple completed phases."""
        phase_completion = {
            0: (15, 12, True),  # Phase 0 complete (15 steps, 12 questions)
            1: (36, 12, True),  # Phase 1 complete (36 steps, 12 questions)
        }

        result = compute_phase_badges(phase_completion)

        badge_ids = {b.id for b in result}
        assert "phase_0_complete" in badge_ids
        assert "phase_1_complete" in badge_ids

    def test_awards_badge_when_exceeds_requirements(self):
        """Should award badge when user exceeds requirements."""
        phase_completion = {
            0: (100, 100, True),  # Way more than needed
        }

        result = compute_phase_badges(phase_completion)

        assert len(result) == 1
        assert result[0].id == "phase_0_complete"


class TestComputeStreakBadges:
    """Tests for compute_streak_badges()."""

    def test_returns_empty_for_zero_streak(self):
        """Should return no badges for zero streak."""
        result = compute_streak_badges(0)

        assert result == []

    def test_returns_empty_for_short_streak(self):
        """Should return no badges for streak < 7 days."""
        result = compute_streak_badges(6)

        assert result == []

    def test_returns_week_warrior_for_7_day_streak(self):
        """Should return Week Warrior badge for 7-day streak."""
        result = compute_streak_badges(7)

        assert len(result) == 1
        assert result[0].id == "streak_7"
        assert result[0].name == "Week Warrior"
        assert result[0].icon == "🔥"

    def test_returns_monthly_master_for_30_day_streak(self):
        """Should return Week Warrior and Monthly Master for 30-day streak."""
        result = compute_streak_badges(30)

        badge_ids = {b.id for b in result}
        assert "streak_7" in badge_ids
        assert "streak_30" in badge_ids
        assert "streak_100" not in badge_ids

    def test_returns_all_streak_badges_for_100_day_streak(self):
        """Should return all streak badges for 100-day streak."""
        result = compute_streak_badges(100)

        badge_ids = {b.id for b in result}
        assert "streak_7" in badge_ids
        assert "streak_30" in badge_ids
        assert "streak_100" in badge_ids

    def test_returns_correct_badge_info(self):
        """Should return correct badge metadata."""
        result = compute_streak_badges(100)

        century_badge = next(b for b in result if b.id == "streak_100")
        assert century_badge.name == "Century Club"
        assert century_badge.description == "Maintained a 100-day learning streak"
        assert century_badge.icon == "💯"


class TestComputeAllBadges:
    """Tests for compute_all_badges()."""

    def test_returns_empty_for_no_progress(self):
        """Should return no badges when no progress."""
        result = compute_all_badges({}, 0)

        assert result == []

    def test_combines_phase_and_streak_badges(self):
        """Should return both phase and streak badges."""
        # Phase 0 requires 15 steps, 12 questions
        phase_completion = {
            0: (15, 12, True),
        }

        result = compute_all_badges(phase_completion, 7)

        badge_ids = {b.id for b in result}
        assert "phase_0_complete" in badge_ids
        assert "streak_7" in badge_ids

    def test_caches_with_user_id(self):
        """Should work with user_id for caching (functional test)."""
        phase_completion = {
            0: (15, 12, True),
        }

        # First call
        result1 = compute_all_badges(phase_completion, 7, user_id="test-user-1")
        # Second call should use cache
        result2 = compute_all_badges(phase_completion, 7, user_id="test-user-1")

        assert len(result1) == len(result2)
        assert {b.id for b in result1} == {b.id for b in result2}

    def test_different_progress_different_results(self):
        """Should return different results for different progress."""
        result1 = compute_all_badges({}, 0, user_id="test-user-2")
        result2 = compute_all_badges({0: (15, 12, True)}, 7, user_id="test-user-3")

        assert len(result2) > len(result1)
