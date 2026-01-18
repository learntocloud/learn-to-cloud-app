"""Tests for services/streaks_service.py - pure function tests."""

from datetime import date, datetime, timedelta

import time_machine

from services.streaks_service import MAX_SKIP_DAYS, calculate_streak_with_forgiveness


class TestCalculateStreakWithForgiveness:
    """Test calculate_streak_with_forgiveness function."""

    # ========== Edge Cases: Empty/Invalid Input ==========

    def test_empty_activity_dates(self):
        """Empty list returns zeros and not alive."""
        current, longest, alive = calculate_streak_with_forgiveness([])
        assert current == 0
        assert longest == 0
        assert alive is False

    # ========== Single Day Activity ==========

    @time_machine.travel("2026-01-17")
    def test_single_activity_today(self):
        """Single activity today = streak of 1, alive."""
        dates = [date(2026, 1, 17)]
        current, longest, alive = calculate_streak_with_forgiveness(dates)
        assert current == 1
        assert longest == 1
        assert alive is True

    @time_machine.travel("2026-01-17")
    def test_single_activity_yesterday(self):
        """Single activity yesterday = streak of 1, alive (within forgiveness)."""
        dates = [date(2026, 1, 16)]
        current, longest, alive = calculate_streak_with_forgiveness(dates)
        assert current == 1
        assert longest == 1
        assert alive is True

    @time_machine.travel("2026-01-17")
    def test_single_activity_2_days_ago(self):
        """Single activity 2 days ago = alive (max forgiveness)."""
        dates = [date(2026, 1, 15)]  # 2 days ago
        current, longest, alive = calculate_streak_with_forgiveness(dates)
        assert current == 1
        assert longest == 1
        assert alive is True

    @time_machine.travel("2026-01-17")
    def test_single_activity_3_days_ago(self):
        """Single activity 3 days ago = dead (beyond forgiveness)."""
        dates = [date(2026, 1, 14)]  # 3 days ago
        current, longest, alive = calculate_streak_with_forgiveness(dates)
        assert current == 0  # Dead
        assert longest == 1  # Was still a streak of 1
        assert alive is False

    # ========== Consecutive Days ==========

    @time_machine.travel("2026-01-17")
    def test_three_consecutive_days(self):
        """Three consecutive days ending today."""
        dates = [date(2026, 1, 17), date(2026, 1, 16), date(2026, 1, 15)]
        current, longest, alive = calculate_streak_with_forgiveness(dates)
        assert current == 3
        assert longest == 3
        assert alive is True

    @time_machine.travel("2026-01-17")
    def test_week_of_consecutive_days(self):
        """A full week of activity."""
        dates = [date(2026, 1, 17 - i) for i in range(7)]
        current, longest, alive = calculate_streak_with_forgiveness(dates)
        assert current == 7
        assert longest == 7
        assert alive is True

    # ========== Forgiveness (Skipped Days Within Tolerance) ==========

    @time_machine.travel("2026-01-17")
    def test_skip_one_day_maintains_streak(self):
        """Skip 1 day within streak still counts as continuous."""
        # Activity on Jan 17, skip 16, activity on Jan 15
        dates = [date(2026, 1, 17), date(2026, 1, 15)]
        current, longest, alive = calculate_streak_with_forgiveness(dates)
        assert current == 2  # Still continuous due to forgiveness
        assert longest == 2
        assert alive is True

    @time_machine.travel("2026-01-17")
    def test_skip_two_days_maintains_streak(self):
        """Skip 2 days (max forgiveness) still counts as continuous."""
        # Activity on Jan 17, skip 16 and 15, activity on Jan 14
        dates = [date(2026, 1, 17), date(2026, 1, 14)]
        current, longest, alive = calculate_streak_with_forgiveness(dates)
        assert current == 2
        assert longest == 2
        assert alive is True

    @time_machine.travel("2026-01-17")
    def test_skip_three_days_breaks_streak(self):
        """Skip 3 days breaks the streak."""
        # Activity on Jan 17, skip 16, 15, 14, activity on Jan 13
        dates = [date(2026, 1, 17), date(2026, 1, 13)]
        current, longest, alive = calculate_streak_with_forgiveness(dates)
        assert current == 1  # Only today counts
        assert longest == 1
        assert alive is True

    # ========== Broken Streak (Historical Gap) ==========

    @time_machine.travel("2026-01-17")
    def test_gap_in_history_preserves_longest(self):
        """Gap in history: current streak is recent, longest includes past."""
        # Recent: Jan 17, 16, 15 (3 days)
        # Gap: Jan 14, 13, 12 (break)
        # Old: Jan 11, 10, 9, 8, 7 (5 days)
        dates = [
            date(2026, 1, 17),
            date(2026, 1, 16),
            date(2026, 1, 15),
            # 3-day gap here
            date(2026, 1, 11),
            date(2026, 1, 10),
            date(2026, 1, 9),
            date(2026, 1, 8),
            date(2026, 1, 7),
        ]
        current, longest, alive = calculate_streak_with_forgiveness(dates)
        assert current == 3  # Recent streak
        assert longest == 5  # Historical longer streak
        assert alive is True

    @time_machine.travel("2026-01-17")
    def test_dead_streak_still_has_longest(self):
        """Dead streak (no recent activity) still reports longest."""
        # Old streak from Jan 1-5 (5 days), no recent activity
        dates = [
            date(2026, 1, 5),
            date(2026, 1, 4),
            date(2026, 1, 3),
            date(2026, 1, 2),
            date(2026, 1, 1),
        ]
        current, longest, alive = calculate_streak_with_forgiveness(dates)
        assert current == 0  # Dead
        assert longest == 5  # Historical best
        assert alive is False

    # ========== Duplicate Dates ==========

    @time_machine.travel("2026-01-17")
    def test_duplicate_dates_deduplicated(self):
        """Multiple activities on same day count as one."""
        dates = [
            date(2026, 1, 17),
            date(2026, 1, 17),  # Duplicate
            date(2026, 1, 17),  # Duplicate
            date(2026, 1, 16),
        ]
        current, longest, alive = calculate_streak_with_forgiveness(dates)
        assert current == 2  # Only 2 unique days
        assert longest == 2
        assert alive is True

    # ========== DateTime Objects (Not Just Dates) ==========

    @time_machine.travel("2026-01-17")
    def test_datetime_objects_converted(self):
        """datetime objects are converted to dates."""
        dates = [
            datetime(2026, 1, 17, 10, 30),
            datetime(2026, 1, 16, 15, 45),
        ]
        current, longest, alive = calculate_streak_with_forgiveness(dates)
        assert current == 2
        assert longest == 2
        assert alive is True

    # ========== Custom Max Skip Days ==========

    @time_machine.travel("2026-01-17")
    def test_custom_max_skip_zero(self):
        """max_skip_days=0 requires consecutive days."""
        dates = [date(2026, 1, 17), date(2026, 1, 15)]  # 1 day gap
        current, longest, alive = calculate_streak_with_forgiveness(
            dates, max_skip_days=0
        )
        assert current == 1  # Gap breaks it
        assert longest == 1
        assert alive is True  # Activity today, so alive (0 days since last)

    @time_machine.travel("2026-01-17")
    def test_custom_max_skip_five(self):
        """max_skip_days=5 allows larger gaps."""
        # 5-day gap between activities
        dates = [date(2026, 1, 17), date(2026, 1, 11)]
        current, longest, alive = calculate_streak_with_forgiveness(
            dates, max_skip_days=5
        )
        assert current == 2  # Still connected
        assert longest == 2
        assert alive is True

    # ========== Unsorted Input ==========

    @time_machine.travel("2026-01-17")
    def test_unsorted_dates_handled(self):
        """Dates don't need to be pre-sorted."""
        dates = [
            date(2026, 1, 15),
            date(2026, 1, 17),  # Most recent
            date(2026, 1, 16),
        ]
        current, longest, alive = calculate_streak_with_forgiveness(dates)
        assert current == 3
        assert longest == 3
        assert alive is True

    # ========== Constants ==========

    def test_max_skip_days_constant(self):
        """MAX_SKIP_DAYS is 2 as documented."""
        assert MAX_SKIP_DAYS == 2


class TestStreakEdgeCases:
    """Additional edge case tests."""

    @time_machine.travel("2026-01-01")
    def test_new_year_boundary(self):
        """Streak across year boundary works."""
        dates = [
            date(2026, 1, 1),
            date(2025, 12, 31),
            date(2025, 12, 30),
        ]
        current, longest, alive = calculate_streak_with_forgiveness(dates)
        assert current == 3
        assert longest == 3
        assert alive is True

    @time_machine.travel("2026-02-28")
    def test_leap_year_february(self):
        """Non-leap year February boundary (2026 is not a leap year)."""
        dates = [
            date(2026, 2, 28),
            date(2026, 2, 27),
        ]
        current, longest, alive = calculate_streak_with_forgiveness(dates)
        assert current == 2
        assert alive is True

    @time_machine.travel("2026-01-17")
    def test_very_long_streak(self):
        """Test with 100+ day streak."""
        dates = [date(2026, 1, 17) - timedelta(days=i) for i in range(100)]
        current, longest, alive = calculate_streak_with_forgiveness(dates)
        assert current == 100
        assert longest == 100
        assert alive is True

    @time_machine.travel("2026-01-17")
    def test_multiple_broken_streaks(self):
        """Multiple distinct streaks in history."""
        dates = [
            # Recent: 3 days
            date(2026, 1, 17),
            date(2026, 1, 16),
            date(2026, 1, 15),
            # Gap
            # Middle: 4 days (longest)
            date(2026, 1, 8),
            date(2026, 1, 7),
            date(2026, 1, 6),
            date(2026, 1, 5),
            # Gap
            # Old: 2 days
            date(2025, 12, 20),
            date(2025, 12, 19),
        ]
        current, longest, alive = calculate_streak_with_forgiveness(dates)
        assert current == 3  # Recent
        assert longest == 4  # Middle was longest
        assert alive is True
