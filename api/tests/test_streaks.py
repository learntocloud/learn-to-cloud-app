"""Tests for streak calculation with forgiveness rules.

Source of truth: .github/skills/streaks/SKILL.md

Key rules from SKILL.md:
- MAX_SKIP_DAYS = 2 (can skip up to 2 consecutive days)
- streak_alive = True if last activity within 2 days
- streak_alive = False (broken) if no activity for 3+ days
- current_streak = 0 when broken, longest_streak preserved
- Multiple activities on same day count as 1 day for streak
- Badges use longest_streak, not current_streak
"""

from datetime import UTC, datetime, timedelta

from services.streaks import MAX_SKIP_DAYS, calculate_streak_with_forgiveness


class TestForgivenessBoundary:
    """Test the 2-day forgiveness boundary from SKILL.md."""

    def test_max_skip_days_is_2(self):
        """SKILL.md: MAX_SKIP_DAYS = 2."""
        assert MAX_SKIP_DAYS == 2

    def test_streak_alive_within_0_days(self):
        """Activity today keeps streak alive."""
        today = datetime.now(UTC).date()
        dates = [today]
        _, _, streak_alive = calculate_streak_with_forgiveness(dates)
        assert streak_alive is True

    def test_streak_alive_within_1_day(self):
        """Activity yesterday keeps streak alive."""
        today = datetime.now(UTC).date()
        dates = [today - timedelta(days=1)]
        _, _, streak_alive = calculate_streak_with_forgiveness(dates)
        assert streak_alive is True

    def test_streak_alive_within_2_days(self):
        """Activity 2 days ago keeps streak alive (at boundary)."""
        today = datetime.now(UTC).date()
        dates = [today - timedelta(days=2)]
        _, _, streak_alive = calculate_streak_with_forgiveness(dates)
        assert streak_alive is True

    def test_streak_broken_after_3_days(self):
        """SKILL.md: No activity for 3+ days = broken."""
        today = datetime.now(UTC).date()
        dates = [today - timedelta(days=3)]
        _, _, streak_alive = calculate_streak_with_forgiveness(dates)
        assert streak_alive is False

    def test_streak_broken_after_many_days(self):
        """Activity long ago means streak is broken."""
        today = datetime.now(UTC).date()
        dates = [today - timedelta(days=30)]
        _, _, streak_alive = calculate_streak_with_forgiveness(dates)
        assert streak_alive is False


class TestStreakCounting:
    """Test streak counting with forgiveness gaps."""

    def test_perfect_consecutive_days(self):
        """SKILL.md Scenario 1: Perfect week with no gaps."""
        today = datetime.now(UTC).date()
        # 7 consecutive days including today
        dates = [today - timedelta(days=i) for i in range(7)]
        current, longest, alive = calculate_streak_with_forgiveness(dates)

        assert current == 7
        assert longest == 7
        assert alive is True

    def test_weekend_break_forgiven(self):
        """SKILL.md Scenario 2: 2-day gap is forgiven.

        Mon ✓  Tue ✓  Wed ✓  Thu ✓  Fri ✓  Sat ✗  Sun ✗  Mon ✓
        → current_streak = 6, streak_alive = True (2-day gap forgiven)
        """
        today = datetime.now(UTC).date()
        # Activity on Mon (today), then skip Sat+Sun, then Mon-Fri last week
        dates = [
            today,  # Mon (today)
            today - timedelta(days=3),  # Fri
            today - timedelta(days=4),  # Thu
            today - timedelta(days=5),  # Wed
            today - timedelta(days=6),  # Tue
            today - timedelta(days=7),  # Mon
        ]
        current, longest, alive = calculate_streak_with_forgiveness(dates)

        assert alive is True
        assert current == 6
        assert longest == 6

    def test_three_day_break_resets_streak(self):
        """SKILL.md Scenario 3: 3-day gap breaks streak.

        Mon ✓  Tue ✓  Wed ✓  ... Sat ✗  Sun ✗  Mon ✗  Tue ✓
        → current_streak = 1, longest_streak = 3, streak_alive = True
        """
        today = datetime.now(UTC).date()
        # Today is Tue, 3-day gap, then 3 consecutive days before
        dates = [
            today,  # Tue (today)
            today - timedelta(days=7),  # Wed last week (3 day gap = break)
            today - timedelta(days=8),  # Tue last week
            today - timedelta(days=9),  # Mon last week
        ]
        current, longest, alive = calculate_streak_with_forgiveness(dates)

        assert alive is True
        assert current == 1  # Only today counts in current streak
        assert longest == 3  # Previous streak preserved


class TestBrokenStreakBehavior:
    """Test behavior when streak is broken."""

    def test_broken_streak_has_zero_current(self):
        """SKILL.md: When streak breaks, current_streak → 0."""
        today = datetime.now(UTC).date()
        # Activity 5 days ago (beyond 2-day forgiveness)
        dates = [
            today - timedelta(days=5),
            today - timedelta(days=6),
            today - timedelta(days=7),
        ]
        current, longest, alive = calculate_streak_with_forgiveness(dates)

        assert alive is False
        assert current == 0
        assert longest == 3

    def test_longest_streak_preserved_when_broken(self):
        """SKILL.md: longest_streak is preserved (all-time high)."""
        today = datetime.now(UTC).date()
        # Had a 10-day streak that ended 5 days ago
        dates = [today - timedelta(days=5 + i) for i in range(10)]
        current, longest, alive = calculate_streak_with_forgiveness(dates)

        assert alive is False
        assert current == 0
        assert longest == 10


class TestMultipleActivitiesSameDay:
    """SKILL.md: Multiple activities on same day count as 1 day."""

    def test_duplicate_dates_counted_once(self):
        """SKILL.md Scenario 4: Multiple activities same day = 1 day.

        Day 1: 5 steps + 2 questions + 1 hands-on
        Day 2: 1 step
        → current_streak = 2 (not 9)
        """
        today = datetime.now(UTC).date()
        yesterday = today - timedelta(days=1)

        # 8 activities on yesterday, 1 activity today
        dates = [
            today,
            yesterday,
            yesterday,
            yesterday,
            yesterday,
            yesterday,
            yesterday,
            yesterday,
            yesterday,
        ]
        current, longest, alive = calculate_streak_with_forgiveness(dates)

        assert current == 2
        assert longest == 2

    def test_datetime_objects_converted_to_dates(self):
        """Datetime objects should be converted to dates for deduplication."""
        today = datetime.now(UTC).date()

        # Multiple datetime objects on same day
        dates = [
            datetime(today.year, today.month, today.day, 10, 0, 0, tzinfo=UTC),
            datetime(today.year, today.month, today.day, 14, 0, 0, tzinfo=UTC),
            datetime(today.year, today.month, today.day, 18, 0, 0, tzinfo=UTC),
        ]
        current, longest, alive = calculate_streak_with_forgiveness(dates)

        assert current == 1
        assert longest == 1


class TestEdgeCases:
    """Edge cases for streak calculation."""

    def test_empty_activity_list(self):
        """No activity = no streak."""
        current, longest, alive = calculate_streak_with_forgiveness([])

        assert current == 0
        assert longest == 0
        assert alive is False

    def test_single_activity_today(self):
        """Single activity today = streak of 1."""
        today = datetime.now(UTC).date()
        current, longest, alive = calculate_streak_with_forgiveness([today])

        assert current == 1
        assert longest == 1
        assert alive is True

    def test_single_activity_old(self):
        """Single old activity = broken streak, longest = 1."""
        today = datetime.now(UTC).date()
        dates = [today - timedelta(days=30)]
        current, longest, alive = calculate_streak_with_forgiveness(dates)

        assert current == 0
        assert longest == 1
        assert alive is False

    def test_activity_dates_sorted_correctly(self):
        """Function should handle unsorted input."""
        today = datetime.now(UTC).date()
        # Deliberately unsorted
        dates = [
            today - timedelta(days=3),
            today,
            today - timedelta(days=1),
            today - timedelta(days=2),
        ]
        current, longest, alive = calculate_streak_with_forgiveness(dates)

        assert current == 4
        assert longest == 4
        assert alive is True

    def test_gaps_at_various_positions(self):
        """Test gaps in middle of activity history."""
        today = datetime.now(UTC).date()
        # Two separate streaks: 3 days now, gap, 5 days before
        dates = [
            today,
            today - timedelta(days=1),
            today - timedelta(days=2),
            # 3-day gap here (breaks streak)
            today - timedelta(days=6),
            today - timedelta(days=7),
            today - timedelta(days=8),
            today - timedelta(days=9),
            today - timedelta(days=10),
        ]
        current, longest, alive = calculate_streak_with_forgiveness(dates)

        assert alive is True
        assert current == 3  # Current active streak
        assert longest == 5  # Longer historical streak


class TestForgivenessWithinStreak:
    """Test that forgiveness applies within a streak chain."""

    def test_one_day_gaps_throughout(self):
        """1-day gaps scattered throughout should be forgiven."""
        today = datetime.now(UTC).date()
        # Activity every other day for 2 weeks
        dates = [today - timedelta(days=i * 2) for i in range(7)]
        current, longest, alive = calculate_streak_with_forgiveness(dates)

        assert alive is True
        assert current == 7
        assert longest == 7

    def test_two_day_gaps_throughout(self):
        """2-day gaps scattered throughout should be forgiven."""
        today = datetime.now(UTC).date()
        # Activity every 3rd day (2-day gaps)
        dates = [today - timedelta(days=i * 3) for i in range(5)]
        current, longest, alive = calculate_streak_with_forgiveness(dates)

        assert alive is True
        assert current == 5
        assert longest == 5

    def test_mixed_gaps(self):
        """Mix of 0, 1, and 2 day gaps should all be forgiven."""
        today = datetime.now(UTC).date()
        dates = [
            today,  # Day 0
            today - timedelta(days=1),  # Day 1 (0-day gap)
            today - timedelta(days=3),  # Day 3 (1-day gap)
            today - timedelta(days=6),  # Day 6 (2-day gap)
        ]
        current, longest, alive = calculate_streak_with_forgiveness(dates)

        assert alive is True
        assert current == 4
        assert longest == 4
