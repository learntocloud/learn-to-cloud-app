"""Streak calculation utilities."""

from datetime import UTC, date, datetime

MAX_SKIP_DAYS = 2


def calculate_streak_with_forgiveness(
    activity_dates: list[date],
    max_skip_days: int = MAX_SKIP_DAYS,
) -> tuple[int, int, bool]:
    """Calculate streak with forgiveness for skipped days.

    SKILL.md source of truth (.github/skills/streaks/SKILL.md):
    - MAX_SKIP_DAYS = 2 (can skip up to 2 consecutive days)
    - streak_alive = True if last activity within max_skip_days of today
    - current_streak = streak from today going backward until 3+ day gap
    - longest_streak = longest streak ever seen (all-time high)
    - When streak breaks (3+ day gap): current_streak = 0, longest preserved

    Args:
        activity_dates: List of dates with activity

    Returns:
        Tuple of (current_streak, longest_streak, streak_alive)
    """
    if not activity_dates:
        return 0, 0, False

    today = datetime.now(UTC).date()

    # Dedupe and sort dates (most recent first)
    unique_dates = sorted(
        set(d.date() if isinstance(d, datetime) else d for d in activity_dates),
        reverse=True,
    )

    if not unique_dates:
        return 0, 0, False

    # Check if streak is alive (last activity within max_skip_days of today)
    most_recent = unique_dates[0]
    days_since_last = (today - most_recent).days
    streak_alive = days_since_last <= max_skip_days

    # Walk through dates to find streaks
    # current_streak: streak from most recent activity going backward (only if alive)
    # longest_streak: longest streak ever found
    longest_streak = 0
    current_streak_length = 1  # Start with first date
    first_gap_found = False

    for i in range(len(unique_dates) - 1):
        current_date = unique_dates[i]
        next_date = unique_dates[i + 1]
        gap = (current_date - next_date).days - 1  # Days between (excluding endpoints)

        if gap <= max_skip_days:
            current_streak_length += 1
        else:
            # Gap breaks the streak
            if not first_gap_found:
                # This was the "current" streak from most recent
                first_gap_found = True
                if current_streak_length > longest_streak:
                    longest_streak = current_streak_length
                # Save current streak before resetting
                current_streak_from_today = current_streak_length
            else:
                if current_streak_length > longest_streak:
                    longest_streak = current_streak_length
            current_streak_length = 1

    # Handle final streak segment
    if current_streak_length > longest_streak:
        longest_streak = current_streak_length

    # Determine current streak
    if not streak_alive:
        current_streak = 0
    elif first_gap_found:
        # There was a gap, so current streak is what we saved
        current_streak = current_streak_from_today
    else:
        # No gaps found, entire history is one continuous streak
        current_streak = current_streak_length

    return current_streak, longest_streak, streak_alive
