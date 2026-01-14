"""Streak calculation utilities."""

from datetime import UTC, date, datetime

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

    unique_dates = sorted(
        set(d.date() if isinstance(d, datetime) else d for d in activity_dates),
        reverse=True,
    )

    if not unique_dates:
        return 0, 0, False

    most_recent = unique_dates[0]
    days_since_last = (today - most_recent).days
    streak_alive = days_since_last <= max_skip_days

    current_streak = 0
    longest_streak = 0
    temp_streak = 1

    for i in range(len(unique_dates) - 1):
        current_date = unique_dates[i]
        next_date = unique_dates[i + 1]
        gap = (current_date - next_date).days - 1

        if gap <= max_skip_days:
            temp_streak += 1
        else:
            if temp_streak > longest_streak:
                longest_streak = temp_streak
            temp_streak = 1

    if temp_streak > longest_streak:
        longest_streak = temp_streak

    if streak_alive:
        current_streak = temp_streak
    else:
        current_streak = 0

    return current_streak, longest_streak, streak_alive
