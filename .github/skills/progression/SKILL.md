---
name: progression
description: Debug and modify the progression system: badges, phase unlocking, content locks. Use when adding phases, changing unlock rules, fixing badge awards, or investigating why content is locked.
---

# Progression System

## Quick Actions

### Validate Phase Requirements Match Content
Run the [check-requirements.sh](./check-requirements.sh) script to verify PHASE_REQUIREMENTS in code matches actual content:
```bash
./.github/skills/progression/check-requirements.sh
```

### Debug Why Content is Locked
1. **Check user's progress:**
   ```bash
   # Query user's completion status (use database skill for full query)
   # Check: steps, questions, hands-on for previous phase
   ```

2. **Verify unlock rules:**
   - Phase 0 → Always unlocked
   - Phases 1-6 → Previous phase must be 100% complete
   - Topics → Previous topic in same phase must be complete
   - Admin users (`is_admin=True`) → Bypass all locks

### Debug Why Badge Not Awarded
A phase badge requires ALL THREE:
1. ✅ All learning steps completed
2. ✅ All knowledge questions passed
3. ✅ All hands-on requirements validated

Check each in order—usually it's a missing hands-on validation.

### Add a New Phase
1. Create content files in `content/phases/phaseN/`
2. Add to `PHASE_REQUIREMENTS` in `api/services/progress.py`
3. Add hands-on requirements to `api/services/hands_on_verification.py`
4. Add badge definition to `api/services/badges.py`
5. Run `check-requirements.sh` to validate

### Change Unlock Rules
Edit unlock logic in:
- `api/services/progress.py` → `is_phase_unlocked()`, `is_topic_unlocked()`
- Update tests in `api/tests/test_progression_system.py`

---

## Reference

### Phase Completion Formula
```
Phase Complete = (Steps + Questions + Hands-on) ALL at 100%
```

### Current Requirements

| Phase | Steps | Questions | Hands-on | Badge |
|-------|-------|-----------|----------|-------|
| 0 | 15 | 12 | 1 | Explorer (Bronze) |
| 1 | 36 | 12 | 3 | Practitioner (Silver) |
| 2 | 30 | 12 | 2 | Builder (Blue) |
| 3 | 31 | 8 | 1 | Specialist (Purple) |
| 4 | 51 | 18 | 1 | Architect (Gold) |
| 5 | 55 | 12 | 4 | Master (Red) |
| 6 | 64 | 12 | 1 | Legend (Rainbow) |

### Key Files to Edit

| Task | File |
|------|------|
| Change phase requirements | `api/services/progress.py` → `PHASE_REQUIREMENTS` |
| Add/modify hands-on checks | `api/services/hands_on_verification.py` |
| Change badge definitions | `api/services/badges.py` |
| Modify unlock logic | `api/services/progress.py` |
| Add GitHub validations | `api/services/github_hands_on_verification.py` |

### Tests
```bash
cd api && .venv/bin/python -m pytest tests/test_progression_system.py -v
cd api && .venv/bin/python -m pytest tests/test_badges.py -v
```
