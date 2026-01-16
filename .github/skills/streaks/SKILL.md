---
name: streaks
description: Debug and modify streak calculation with forgiveness rules. Use when changing streak logic, adding streak badges, fixing streak resets, or investigating why a streak was lost.
---

# Streaks System

## Quick Actions

### Debug Why a Streak Reset
1. **Check user's activity dates:**
   ```sql
   SELECT activity_date, activity_type
   FROM user_activities
   WHERE user_id = 'USER_ID'
   ORDER BY activity_date DESC LIMIT 20;
   ```

2. **Look for 3+ day gaps** — forgiveness allows 2 days max:
   - Gap of 1-2 days → Streak continues
   - Gap of 3+ days → Streak breaks

3. **Check timezone** — activities logged in UTC, user may be in different TZ

### Test Streak Calculation
```bash
cd api && .venv/bin/python -c "
from datetime import date, timedelta
from services.streaks import calculate_streak_with_forgiveness

# Test: activity with 2-day gap (should NOT break)
dates = [date.today(), date.today() - timedelta(days=3)]
current, longest, alive = calculate_streak_with_forgiveness(dates)
print(f'2-day gap: current={current}, longest={longest}, alive={alive}')

# Test: activity with 3-day gap (should break)
dates = [date.today(), date.today() - timedelta(days=4)]
current, longest, alive = calculate_streak_with_forgiveness(dates)
print(f'3-day gap: current={current}, longest={longest}, alive={alive}')
"
```

### Change Forgiveness Window
Edit `MAX_SKIP_DAYS` in `api/services/streaks.py`:
```python
MAX_SKIP_DAYS = 2  # Change this value
```

### Add a New Streak Badge
1. Add to `STREAK_BADGES` in `api/services/badges.py`:
   ```python
   Badge(id="streak_365", name="Year Champion", icon="🏆", tier="platinum")
   ```
2. Add threshold to `compute_streak_badges()` function
3. Add test in `api/tests/test_streaks.py`

### Add a New Activity Type
1. Add to `ActivityType` enum in `api/models.py`
2. Call `log_activity()` where the action occurs
3. Activity automatically counts toward streaks

---

## Reference

### Forgiveness Rule
| Gap | Result |
|-----|--------|
| 0 days (consecutive) | ✅ Streak continues |
| 1-2 days | ✅ Streak continues (forgiven) |
| 3+ days | ❌ Streak breaks, resets to 0 |

### Activity Types That Count
| Type | When Logged |
|------|-------------|
| `STEP_COMPLETE` | Checkbox checked |
| `QUESTION_ATTEMPT` | Answer submitted |
| `TOPIC_COMPLETE` | All steps + questions done |
| `HANDS_ON_VALIDATED` | Submission approved |
| `PHASE_COMPLETE` | All requirements met |

**Note:** Multiple activities on same day = 1 day for streak purposes.

### Streak Badges
| Badge | Days Required |
|-------|---------------|
| Week Warrior 🔥 | 7 |
| Monthly Master 💪 | 30 |
| Century Club 💯 | 100 |

Badges are permanent—breaking streak doesn't revoke them.

### Key Files to Edit

| Task | File |
|------|------|
| Change calculation logic | `api/services/streaks.py` |
| Add activity types | `api/models.py` → `ActivityType` |
| Log new activities | `api/services/activity.py` |
| Modify streak badges | `api/services/badges.py` |

### Tests
```bash
cd api && .venv/bin/python -m pytest tests/test_streaks.py -v
```
