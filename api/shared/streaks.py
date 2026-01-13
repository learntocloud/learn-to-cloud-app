"""Streak calculation utilities."""

from datetime import UTC, date, datetime

# Streak forgiveness: allow up to 2 days skipped per week
MAX_SKIP_DAYS = 2


def calculate_streak_with_forgiveness(
    activity_dates: list[date],
    max_skip_days: int = MAX_SKIP_DAYS,
) -> tuple[int, int, bool]:
    """Calculate streak with forgiveness for skipped days.

    Args:
        activity_dates: List of dates with activity (sorted descending)
        max_skip_days: Maximum consecutive days that can be skipped

    Returns:
        Tuple of (current_streak, longest_streak, streak_alive)
    """
    if not activity_dates:
        return 0, 0, False

    today = datetime.now(UTC).date()

    # Convert to dates and remove duplicates
    unique_dates = sorted(
        set(d.date() if isinstance(d, datetime) else d for d in activity_dates),
        reverse=True,
    )

    if not unique_dates:
        return 0, 0, False

    # Check if streak is still alive (activity within forgiveness window)
    most_recent = unique_dates[0]
    days_since_last = (today - most_recent).days
    streak_alive = days_since_last <= max_skip_days

    # Calculate current streak
    current_streak = 0
    longest_streak = 0
    temp_streak = 1  # Start with 1 for the first day

    # Start from most recent and work backwards
    for i in range(len(unique_dates) - 1):
        current_date = unique_dates[i]
        next_date = unique_dates[i + 1]
        gap = (current_date - next_date).days - 1  # Days between (excluding both dates)

        if gap <= max_skip_days:
            # Continue streak (count actual activity days, not gap)
            temp_streak += 1
        else:
            # Streak broken
            if temp_streak > longest_streak:
                longest_streak = temp_streak
            temp_streak = 1

    # Final check for longest
    if temp_streak > longest_streak:
        longest_streak = temp_streak

    # Current streak only counts if still alive
    if streak_alive:
        current_streak = temp_streak
    else:
        current_streak = 0

    return current_streak, longest_streak, streak_alive
