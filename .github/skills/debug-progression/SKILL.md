---
name: debug-progression
description: Debug progression issues: locked content, missing badges, streak resets. Use when investigating why phase is locked, badge not awarded, or streak was lost.
---

# Debug Progression & Streaks

## Validate Requirements Match Content

```bash
./.github/skills/debug-progression/check-requirements.sh
```

## Debug: Why is Content Locked?

1. Phase 0 → Always unlocked
2. Phases 1-6 → Previous phase must be 100% complete (steps + questions + hands-on)
3. Admin users (`is_admin=True`) → Bypass all locks

Check user's progress with `query-db` skill.

## Debug: Why No Badge?

Phase badge requires ALL THREE at 100%:
1. ✅ Learning steps completed
2. ✅ Knowledge questions passed
3. ✅ Hands-on requirements validated

Usually it's a missing hands-on validation.

## Debug: Why Did Streak Reset?

**Forgiveness rule:** Gap of 1-2 days is forgiven, 3+ days breaks streak.

```sql
-- Check user's activity gaps
SELECT activity_date, activity_type
FROM user_activities
WHERE user_id = 'USER_ID'
ORDER BY activity_date DESC LIMIT 20;
```

Test streak calculation:
```bash
cd api && .venv/bin/python -c "
from datetime import date, timedelta
from services.streaks import calculate_streak_with_forgiveness

dates = [date.today(), date.today() - timedelta(days=3)]  # 2-day gap
current, longest, alive = calculate_streak_with_forgiveness(dates)
print(f'current={current}, longest={longest}, alive={alive}')
"
```

## Phase Requirements

| Phase | Steps | Questions | Hands-on | Badge |
|-------|-------|-----------|----------|-------|
| 0 | 15 | 12 | 1 | Explorer 🥉 |
| 1 | 36 | 12 | 3 | Practitioner 🥈 |
| 2 | 30 | 12 | 2 | Builder 🔵 |
| 3 | 31 | 8 | 1 | Specialist 🟣 |
| 4 | 51 | 18 | 1 | Architect 🥇 |
| 5 | 55 | 12 | 4 | Master 🔴 |
| 6 | 64 | 12 | 1 | Legend 🌈 |

## Streak Badges

| Badge | Days |
|-------|------|
| Week Warrior 🔥 | 7 |
| Monthly Master 💪 | 30 |
| Century Club 💯 | 100 |

## Key Files

| What | File |
|------|------|
| Phase requirements | `api/services/progress.py` → `PHASE_REQUIREMENTS` |
| Unlock logic | `api/services/progress.py` → `is_phase_unlocked()` |
| Hands-on checks | `api/services/hands_on_verification.py` |
| Badge definitions | `api/services/badges.py` |
| Streak calculation | `api/services/streaks.py` |
| Forgiveness window | `api/services/streaks.py` → `MAX_SKIP_DAYS` |

## Tests

```bash
cd api && .venv/bin/python -m pytest tests/test_progression_system.py tests/test_badges.py tests/test_streaks.py -v
```
