"""Property-based tests for streaks_service using Hypothesis.

These tests verify mathematical properties that must always hold,
regardless of the input data. They complement the example-based tests
by exploring edge cases automatically.
"""

from datetime import date, timedelta

import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from services.streaks_service import (
    calculate_streak_with_forgiveness,
)

# Mark all tests in this module as unit tests (no database required)
pytestmark = pytest.mark.unit

# =============================================================================
# Custom Strategies
# =============================================================================


@st.composite
def date_lists(draw, min_size: int = 0, max_size: int = 50) -> list[date]:
    """Generate lists of dates within a reasonable range."""
    # Use today's date so streak calculations work correctly
    base_date = date.today()
    num_dates = draw(st.integers(min_value=min_size, max_value=max_size))

    dates = []
    for _ in range(num_dates):
        # Generate dates within last year (reduced range for speed)
        days_ago = draw(st.integers(min_value=0, max_value=365))
        dates.append(base_date - timedelta(days=days_ago))

    return dates


@st.composite
def consecutive_date_lists(
    draw, min_length: int = 1, max_length: int = 30
) -> list[date]:
    """Generate lists of consecutive dates (perfect streaks)."""
    base_date = date.today()
    length = draw(st.integers(min_value=min_length, max_value=max_length))

    return [base_date - timedelta(days=i) for i in range(length)]


# Default settings for property tests - suppress slow health check
hypothesis_settings = settings(
    max_examples=100,
    suppress_health_check=[HealthCheck.too_slow],
)


# =============================================================================
# Property Tests
# =============================================================================


class TestStreakInvariants:
    """Test mathematical invariants that must always hold."""

    @given(dates=date_lists())
    @hypothesis_settings
    def test_longest_streak_gte_current_streak(self, dates: list[date]):
        """Property: longest_streak >= current_streak always."""
        current, longest, _ = calculate_streak_with_forgiveness(dates)

        assert longest >= current, (
            f"Invariant violated: longest ({longest}) < current ({current}) "
            f"for dates: {sorted(set(dates), reverse=True)[:10]}..."
        )

    @given(dates=date_lists())
    @hypothesis_settings
    def test_streaks_are_non_negative(self, dates: list[date]):
        """Property: all streak values are non-negative."""
        current, longest, _ = calculate_streak_with_forgiveness(dates)

        assert current >= 0, f"current_streak is negative: {current}"
        assert longest >= 0, f"longest_streak is negative: {longest}"

    @given(dates=date_lists())
    @hypothesis_settings
    def test_longest_streak_bounded_by_unique_dates(self, dates: list[date]):
        """Property: longest_streak <= number of unique dates."""
        current, longest, _ = calculate_streak_with_forgiveness(dates)
        unique_count = len(set(dates))

        assert (
            longest <= unique_count
        ), f"longest_streak ({longest}) > unique dates ({unique_count})"

    @given(dates=date_lists(min_size=0, max_size=0))
    @hypothesis_settings
    def test_empty_list_returns_zeros(self, dates: list[date]):
        """Property: empty list always returns (0, 0, False)."""
        current, longest, alive = calculate_streak_with_forgiveness(dates)

        assert current == 0
        assert longest == 0
        assert alive is False

    @given(dates=consecutive_date_lists())
    @hypothesis_settings
    def test_consecutive_dates_form_perfect_streak(self, dates: list[date]):
        """Property: consecutive dates starting from today form a perfect streak."""
        current, longest, alive = calculate_streak_with_forgiveness(dates)

        expected_length = len(dates)
        assert (
            current == expected_length
        ), f"Expected streak of {expected_length}, got {current}"
        assert longest == expected_length
        assert alive is True


class TestStreakIdempotency:
    """Test idempotency and ordering properties."""

    @given(dates=date_lists(min_size=1))
    @hypothesis_settings
    def test_duplicate_dates_dont_increase_streak(self, dates: list[date]):
        """Property: adding duplicate dates doesn't change streak."""
        # Get result with original dates
        current1, longest1, alive1 = calculate_streak_with_forgiveness(dates)

        # Add duplicates
        dates_with_dupes = dates + dates
        current2, longest2, alive2 = calculate_streak_with_forgiveness(dates_with_dupes)

        assert current1 == current2, "Duplicates changed current streak"
        assert longest1 == longest2, "Duplicates changed longest streak"
        assert alive1 == alive2, "Duplicates changed alive status"

    @given(dates=date_lists(min_size=2))
    @hypothesis_settings
    def test_order_independent(self, dates: list[date]):
        """Property: streak calculation is order-independent."""
        import random

        # Get result with original order
        current1, longest1, alive1 = calculate_streak_with_forgiveness(dates)

        # Shuffle and recalculate
        shuffled = dates.copy()
        random.shuffle(shuffled)
        current2, longest2, alive2 = calculate_streak_with_forgiveness(shuffled)

        assert current1 == current2, "Order affected current streak"
        assert longest1 == longest2, "Order affected longest streak"
        assert alive1 == alive2, "Order affected alive status"


class TestStreakAliveProperty:
    """Test the streak_alive flag behavior."""

    @given(dates=date_lists(min_size=1))
    @hypothesis_settings
    def test_alive_implies_current_gte_one_or_within_forgiveness(
        self, dates: list[date]
    ):
        """Property: if alive is True, current >= 1."""
        current, _, alive = calculate_streak_with_forgiveness(dates)

        if alive:
            assert current >= 1, f"Streak alive but current={current}"

    @given(dates=date_lists())
    @hypothesis_settings
    def test_dead_streak_has_zero_current(self, dates: list[date]):
        """Property: if alive is False, current == 0."""
        current, _, alive = calculate_streak_with_forgiveness(dates)

        if not alive:
            assert current == 0, f"Streak dead but current={current}"
