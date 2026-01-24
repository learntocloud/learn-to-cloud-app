"""Tests for streaks_service.

Tests streak calculation algorithm with forgiveness rules.
These are pure function tests - no database required.

Uses time_machine to freeze time for deterministic tests.
"""

from datetime import UTC, date, datetime, timedelta

import pytest
import time_machine

from services.streaks_service import (
    INITIAL_STREAK,
    MAX_SKIP_DAYS,
    calculate_streak_with_forgiveness,
)

# Mark all tests in this module as unit tests (no database required)
pytestmark = [
    pytest.mark.unit,
    pytest.mark.usefixtures("freeze_time"),
]

# Fixed reference date for deterministic tests
FROZEN_DATE = datetime(2026, 1, 23, 12, 0, 0, tzinfo=UTC)


@pytest.fixture
def freeze_time():
    """Freeze time to a fixed date for deterministic tests."""
    with time_machine.travel(FROZEN_DATE, tick=False):
        yield


def utc_today() -> date:
    """Get today's date in UTC (matches streak service behavior)."""
    return datetime.now(UTC).date()


class TestCalculateStreakWithForgiveness:
    """Tests for calculate_streak_with_forgiveness()."""

    def test_returns_zeros_for_empty_list(self):
        """Should return zeros for user with no activities."""
        current, longest, alive = calculate_streak_with_forgiveness([])

        assert current == 0
        assert longest == 0
        assert alive is False

    def test_single_activity_today(self):
        """Should return 1-day streak for activity today."""
        today = utc_today()

        current, longest, alive = calculate_streak_with_forgiveness([today])

        assert current == 1
        assert longest == 1
        assert alive is True

    @pytest.mark.parametrize(
        "days_ago,expected_current,expected_longest,expected_alive",
        [
            (1, 1, 1, True),
            (2, 1, 1, True),
            (3, 0, 1, False),
        ],
        ids=["yesterday", "two_days_ago", "three_days_ago"],
    )
    def test_single_activity_days_ago(
        self,
        days_ago: int,
        expected_current: int,
        expected_longest: int,
        expected_alive: bool,
    ):
        """Should handle a single activity with forgiveness window."""
        activity_date = utc_today() - timedelta(days=days_ago)

        current, longest, alive = calculate_streak_with_forgiveness([activity_date])

        assert current == expected_current
        assert longest == expected_longest
        assert alive is expected_alive

    def test_consecutive_days(self):
        """Should count consecutive days as streak."""
        today = utc_today()
        dates = [
            today,
            today - timedelta(days=1),
            today - timedelta(days=2),
        ]

        current, longest, alive = calculate_streak_with_forgiveness(dates)

        assert current == 3
        assert longest == 3
        assert alive is True

    @pytest.mark.parametrize(
        "gap_days,expected_current,expected_longest,expected_alive",
        [
            (1, 2, 2, True),
            (2, 2, 2, True),
            (3, 1, 1, True),
        ],
        ids=["one_day_gap", "two_day_gap", "three_day_gap"],
    )
    def test_forgiveness_gap_rules(
        self,
        gap_days: int,
        expected_current: int,
        expected_longest: int,
        expected_alive: bool,
    ):
        """Should apply forgiveness rules for gaps between activities."""
        today = utc_today()
        dates = [
            today,
            today - timedelta(days=gap_days + 1),
        ]

        current, longest, alive = calculate_streak_with_forgiveness(dates)

        assert current == expected_current
        assert longest == expected_longest
        assert alive is expected_alive

    def test_preserves_longest_streak(self):
        """Should preserve longest streak even when current is shorter."""
        today = utc_today()
        # Old streak: 5 consecutive days, 20 days ago
        old_streak = [today - timedelta(days=20 + i) for i in range(5)]
        # Current: just today (big gap breaks it)
        dates = [today] + old_streak

        current, longest, alive = calculate_streak_with_forgiveness(dates)

        assert current == 1  # Only today
        assert longest == 5  # Old streak preserved
        assert alive is True

    def test_current_streak_is_zero_when_dead(self):
        """Should return current=0 when streak is dead."""
        today = utc_today()
        dates = [today - timedelta(days=5)]  # 5 days ago = dead

        current, longest, alive = calculate_streak_with_forgiveness(dates)

        assert current == 0
        assert longest == 1
        assert alive is False

    def test_deduplicates_dates(self):
        """Should handle duplicate dates correctly."""
        today = utc_today()
        dates = [today, today, today]  # Same day multiple times

        current, longest, alive = calculate_streak_with_forgiveness(dates)

        assert current == 1  # Only counts as 1 day
        assert longest == 1
        assert alive is True

    def test_handles_unsorted_dates(self):
        """Should handle unsorted date list."""
        today = utc_today()
        dates = [
            today - timedelta(days=1),
            today,  # Out of order
            today - timedelta(days=2),
        ]

        current, longest, alive = calculate_streak_with_forgiveness(dates)

        assert current == 3
        assert longest == 3
        assert alive is True

    def test_complex_scenario_multiple_streaks(self):
        """Should correctly identify longest among multiple broken streaks."""
        today = utc_today()
        # Current streak: 2 days
        current_dates = [today, today - timedelta(days=1)]
        # Gap of 4 days (breaks)
        # Old streak: 4 days
        old_dates = [today - timedelta(days=6 + i) for i in range(4)]
        # Gap of 5 days (breaks)
        # Oldest streak: 3 days
        oldest_dates = [today - timedelta(days=15 + i) for i in range(3)]

        dates = current_dates + old_dates + oldest_dates

        current, longest, alive = calculate_streak_with_forgiveness(dates)

        assert current == 2  # Current streak
        assert longest == 4  # Longest was the middle one
        assert alive is True

    def test_max_skip_days_parameter(self):
        """Should respect custom max_skip_days parameter."""
        today = utc_today()
        dates = [
            today,
            today - timedelta(days=5),  # 4-day gap
        ]

        # Default (max_skip_days=2) should break
        current_default, longest_default, alive_default = (
            calculate_streak_with_forgiveness(dates)
        )
        assert current_default == 1

        # Custom (max_skip_days=4) should NOT break
        current_custom, longest_custom, alive_custom = (
            calculate_streak_with_forgiveness(dates, max_skip_days=4)
        )
        assert current_custom == 2

    def test_constants_match_expected_values(self):
        """Should have correct constant values."""
        assert MAX_SKIP_DAYS == 2
        assert INITIAL_STREAK == 1
