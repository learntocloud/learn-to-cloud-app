---
name: streaks
description: Understand how Learn to Cloud calculates learning streaks with forgiveness rules, awards streak badges, and displays activity heatmaps. Use when working on streak calculation, activity logging, heatmap display, or troubleshooting why a streak was lost/maintained.
---

# Streaks System

## Core Concept

Streaks track **consecutive days** of learning activity with a **forgiveness rule** that allows skipping up to 2 days without breaking the streak.

## Forgiveness Rule

| Setting | Value | Purpose |
|---------|-------|---------|
| `MAX_SKIP_DAYS` | 2 | Maximum consecutive days that can be skipped |

**Why forgiveness?** Life happens. Weekends, illness, busy days shouldn't reset weeks of progress. The 2-day forgiveness balances consistency with flexibility.

## Streak States

| State | Condition | `streak_alive` |
|-------|-----------|----------------|
| **Active** | Last activity within 2 days | `True` |
| **Broken** | No activity for 3+ days | `False` |

When a streak breaks:
- `current_streak` → 0
- `longest_streak` → preserved (all-time high)

## Calculation Algorithm

```python
# Simplified from api/services/streaks.py

def calculate_streak_with_forgiveness(activity_dates, max_skip_days=2):
    """
    Returns: (current_streak, longest_streak, streak_alive)
    """
    # 1. Dedupe and sort dates (most recent first)
    unique_dates = sorted(set(activity_dates), reverse=True)
    
    # 2. Check if streak is alive (last activity within max_skip_days)
    days_since_last = (today - most_recent).days
    streak_alive = days_since_last <= max_skip_days
    
    # 3. Walk through dates, counting streak length
    # Gap of 0-2 days = streak continues
    # Gap of 3+ days = streak breaks
    
    # 4. Return current (if alive) or 0, plus longest ever
```

## What Counts as Activity?

Activities logged to `user_activities` table:

| Activity Type | Description | When Logged |
|---------------|-------------|-------------|
| `STEP_COMPLETE` | Completed a learning step | Checkbox checked |
| `QUESTION_ATTEMPT` | Attempted a knowledge question | Answer submitted |
| `TOPIC_COMPLETE` | Finished a topic | All steps + questions done |
| `HANDS_ON_VALIDATED` | Validated a hands-on submission | Submission approved |
| `PHASE_COMPLETE` | Completed a phase | All requirements met |
| `CERTIFICATE_EARNED` | Earned a certificate | Certificate issued |

**Key insight:** Multiple activities on the same day count as **1 day** for streak purposes.

## Streak Badges

Badges awarded based on **longest streak** (all-time):

| Badge | Required Streak | Icon | Name |
|-------|-----------------|------|------|
| `streak_7` | 7 days | 🔥 | Week Warrior |
| `streak_30` | 30 days | 💪 | Monthly Master |
| `streak_100` | 100 days | 💯 | Century Club |

**Note:** Badges are permanent once earned. Breaking your streak doesn't revoke badges.

## Data Flow

```
User Action (step, question, etc.)
       ↓
log_activity() → user_activities table
       ↓
get_streak_data() → calculate_streak_with_forgiveness()
       ↓
StreakData { current_streak, longest_streak, streak_alive }
       ↓
compute_streak_badges(longest_streak) → Badge[]
```

## Key Files

| File | Purpose |
|------|---------|
| [api/services/streaks.py](../../../api/services/streaks.py) | Core streak calculation logic |
| [api/services/activity.py](../../../api/services/activity.py) | Activity logging & heatmap data |
| [api/services/badges.py](../../../api/services/badges.py) | Streak badge definitions & computation |
| [api/models.py](../../../api/models.py) | `ActivityType` enum, `UserActivity` model |
| [api/repositories/activity.py](../../../api/repositories/activity.py) | Database queries for activities |

## Heatmap Data

The activity heatmap (GitHub-style contribution graph) uses the same activity data:

```python
async def get_heatmap_data(db, user_id, days=365) -> HeatmapData:
    """Returns activity counts per day for the last N days."""
    # Aggregates by date, returns:
    # - days: list of {date, count, activity_types}
    # - total_activities: sum of all counts
```

## Example Scenarios

### Scenario 1: Perfect Week
```
Mon ✓  Tue ✓  Wed ✓  Thu ✓  Fri ✓  Sat ✓  Sun ✓
→ current_streak = 7, streak_alive = True
```

### Scenario 2: Weekend Break (forgiveness applies)
```
Mon ✓  Tue ✓  Wed ✓  Thu ✓  Fri ✓  Sat ✗  Sun ✗  Mon ✓
→ current_streak = 6, streak_alive = True (2-day gap forgiven)
```

### Scenario 3: 3-Day Break (streak breaks)
```
Mon ✓  Tue ✓  Wed ✓  ... Sat ✗  Sun ✗  Mon ✗  Tue ✓
→ current_streak = 1, longest_streak = 3, streak_alive = True
```

### Scenario 4: Multiple activities same day
```
Day 1: 5 steps + 2 questions + 1 hands-on
Day 2: 1 step
→ current_streak = 2 (not 9)
```

## Testing Streaks

Run streak tests:
```bash
cd api && .venv/bin/python -m pytest tests/test_streaks.py -v
```

Manual verification:
```bash
cd api && .venv/bin/python -c "
from datetime import date, timedelta
from services.streaks import calculate_streak_with_forgiveness

# Simulate: activity every day for a week
dates = [date.today() - timedelta(days=i) for i in range(7)]
current, longest, alive = calculate_streak_with_forgiveness(dates)
print(f'Current: {current}, Longest: {longest}, Alive: {alive}')
"
```

## Common Issues

### "My streak reset but I only missed 2 days!"
- Check timezone: activities are logged in UTC
- Missing day 1 + 2 = OK, missing day 3 = break

### "Streak shows 0 but I was active yesterday"
- `streak_alive` may be True but `current_streak` calculation counts activity chain
- Check if previous activities had 3+ day gaps

### "Badge not awarded at streak 7"
- Badges use `longest_streak`, not `current_streak`
- Verify with: `SELECT MAX(longest_streak) FROM user_streak_history`
