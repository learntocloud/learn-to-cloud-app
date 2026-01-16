---
name: progression-system
description: Understand how Learn to Cloud tracks progress, awards badges, unlocks content, and determines phase completion. Use when working on badge logic, phase unlocking, progress calculation, certificate eligibility, or troubleshooting why content is locked/unlocked.
---

# Progression System

## Core Concept

A **Phase is Complete** when ALL three requirements are met:
1. ✅ All **Learning Steps** completed
2. ✅ All **Knowledge Questions** passed
3. ✅ All **Hands-on Requirements** validated

This single definition drives: badges, unlocking, profile stats, and certificates.

## Content Hierarchy

```
Phases (7 total: 0-6)
├── Topics (multiple per phase)
│   ├── Learning Steps (checkboxes)
│   └── Knowledge Questions (must pass)
└── Hands-on Requirements (validated submissions)
```

## Unlocking Rules

| Content | Rule |
|---------|------|
| Phase 0 | Always unlocked |
| Phases 1-6 | Previous phase must be complete |
| First topic in phase | Always unlocked |
| Subsequent topics | Previous topic complete (steps + questions) |
| Admin users | Bypass all locks (`is_admin=True`) |

## Progress Calculation

**Topic Progress:**
```
(Steps Completed + Questions Passed) / (Total Steps + Total Questions)
```

**Phase Progress:**
```
(Steps + Questions + Hands-on Validated) / (Total Steps + Total Questions + Total Hands-on)
```

## Badge System

Badges awarded when phase reaches 100% completion:

| Phase | Badge | Tier |
|-------|-------|------|
| 0 | Explorer | Bronze |
| 1 | Practitioner | Silver |
| 2 | Builder | Blue |
| 3 | Specialist | Purple |
| 4 | Architect | Gold |
| 5 | Master | Red |
| 6 | Legend | Rainbow |

## Phase Requirements

Defined in `api/services/progress.py` (PHASE_REQUIREMENTS) and `api/services/hands_on_verification.py` (HANDS_ON_REQUIREMENTS):

| Phase | Steps | Questions | Hands-on |
|-------|-------|-----------|----------|
| 0 | 15 | 12 | 1 |
| 1 | 36 | 12 | 3 |
| 2 | 30 | 12 | 2 |
| 3 | 31 | 8 | 1 |
| 4 | 51 | 18 | 1 |
| 5 | 55 | 12 | 4 |
| 6 | 64 | 12 | 1 |

## Verification Commands

Count steps/questions from content:
```bash
cd frontend/content/phases
for phase in phase0 phase1 phase2 phase3 phase4 phase5 phase6; do
    total_steps=0; total_questions=0
    for f in $phase/*.json; do
        [[ "$f" == *"index.json" ]] && continue
        steps=$(jq '.learning_steps | length' "$f" 2>/dev/null || echo 0)
        questions=$(jq '.questions | length' "$f" 2>/dev/null || echo 0)
        total_steps=$((total_steps + steps))
        total_questions=$((total_questions + questions))
    done
    echo "$phase: $total_steps steps, $total_questions questions"
done
```

Count hands-on requirements:
```bash
cd api && .venv/bin/python -c "
from services.hands_on_verification import HANDS_ON_REQUIREMENTS
for phase_id in sorted(HANDS_ON_REQUIREMENTS.keys()):
    print(f'phase{phase_id}: {len(HANDS_ON_REQUIREMENTS[phase_id])} hands-on requirements')
"
```

## Key Files

### API (Backend)

| Purpose | File |
|---------|------|
| Progress calculation | `api/services/progress.py` |
| Hands-on requirements | `api/services/hands_on_verification.py` |
| GitHub validations | `api/services/github_hands_on_verification.py` |
| Badge computation | `api/services/badges.py` |
| Verification types | `api/models.py` (SubmissionType, ActivityType enums) |
| Certificate eligibility | `api/services/certificates.py` |
| Question grading | `api/services/questions.py` |
| Step tracking | `api/services/steps.py` |

### Routes (API Endpoints)

| Endpoint Prefix | File | Purpose |
|-----------------|------|---------|
| `/api/user` | `api/routes/users.py` | User info, public profiles |
| `/api/github` | `api/routes/github.py` | Hands-on submissions |
| `/api/questions` | `api/routes/questions.py` | Question submission & status |
| `/api/steps` | `api/routes/steps.py` | Step completion tracking |
| `/api/activity` | `api/routes/activity.py` | Streaks & heatmap |
| `/api/certificates` | `api/routes/certificates.py` | Certificate generation |

### Repositories (Database Layer)

| Purpose | File |
|---------|------|
| Progress queries | `api/repositories/progress.py` |
| Submissions | `api/repositories/submission.py` |
| User operations | `api/repositories/user.py` |
| Activity tracking | `api/repositories/activity.py` |
| Certificate storage | `api/repositories/certificate.py` |

### Frontend

| Purpose | File |
|---------|------|
| API calls | `frontend/src/lib/api.ts` |
| Type definitions | `frontend/src/lib/types.ts` |
| Progress calculation | `frontend/src/lib/api.ts` (`calculatePhaseProgress`) |

## Troubleshooting

**Badge not showing:**
1. Check all steps completed for phase
2. Check all questions passed for phase
3. Check all hands-on requirements validated
4. Verify PHASE_REQUIREMENTS matches content

**Content locked unexpectedly:**
1. Check previous topic/phase completion
2. Verify steps AND questions are done (not just one)
3. Check hands-on validation for phase unlocking
4. Check `is_admin` flag if admin bypass not working
