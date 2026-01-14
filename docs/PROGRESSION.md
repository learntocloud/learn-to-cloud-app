# Progression System

This document explains how progress tracking, phase completion, badges, and content unlocking work in Learn to Cloud.

## Overview

Learn to Cloud uses a unified progression model where a **Phase is Complete** when all three requirements are met:

1. ✅ All **Learning Steps** completed
2. ✅ All **Knowledge Questions** passed
3. ✅ All **GitHub Requirements** validated

This unified definition is the single source of truth for:
- Badge awards
- Phase completion status
- Content unlocking
- Profile statistics

---

## Content Hierarchy

```
Phases (7 total: 0-6)
└── Topics (multiple per phase)
    ├── Learning Steps (checkboxes to complete)
    ├── Learning Objectives (informational, not tracked)
    └── Knowledge Questions (must pass to complete topic)
```

### Phases

The curriculum is organized into 7 phases (0-6), each focusing on a different aspect of cloud engineering:

| Phase | Focus Area |
|-------|-----------|
| 0 | Foundations (Linux, Networking, Programming basics) |
| 1 | Cloud Fundamentals (CLI, IaC basics) |
| 2 | Cloud Platform Deep Dive |
| 3 | DevOps Practices |
| 4 | Security & Compliance |
| 5 | Advanced Topics |
| 6 | Capstone & Career |

### Topics

Each phase contains multiple topics that must be completed in order. A topic is complete when:
- All learning steps are marked complete
- All knowledge questions are passed

### GitHub Requirements

Some phases require hands-on verification through GitHub submissions (profile READMEs, repo forks, or deployed apps). These must be validated before a phase is considered complete.

---

## Unlocking Rules

### Phase Unlocking

- **Phase 0**: Always unlocked (starting point)
- **Phases 1-6**: Unlocked when the previous phase is **complete** (steps + questions + GitHub validated)

### Topic Unlocking

Within a phase:
- **First topic**: Always unlocked
- **Subsequent topics**: Unlocked when the previous topic is complete (all steps + all questions)

### Admin Bypass

Users with `is_admin=True` bypass all content locks and can access any phase or topic.

---

## Progress Calculation

### Topic Progress

```
Topic Progress = (Steps Completed + Questions Passed) / (Total Steps + Total Questions)
```

A topic shows status:
- **not_started**: No steps or questions completed
- **in_progress**: Some steps or questions completed
- **completed**: All steps AND all questions done

### Phase Progress

Phase progress is calculated as a single percentage that includes **all** requirements:

```
If phase has GitHub requirements:
  Phase Progress = (Steps Completed + Questions Passed + GitHub Validated) / (Total Steps + Total Questions + 1)

If phase has NO GitHub requirements:
  Phase Progress = (Steps Completed + Questions Passed) / (Total Steps + Total Questions)
```

**Examples:**
- Phase has 31 steps, 8 questions, and GitHub requirement (total = 40 items)
- All steps/questions done but GitHub not validated: 39/40 = **97.5%**
- All steps/questions done AND GitHub validated: 40/40 = **100%**

A phase shows status:
- **not_started**: No progress made
- **in_progress**: Some items completed but not all
- **completed**: All steps + all questions + GitHub validated (if required) = 100%

---

## Badge System

Badges are awarded when a phase meets all completion criteria.

### Badge Criteria

For each phase (0-6), a badge is earned when:
1. Steps completed ≥ Required steps for that phase
2. Questions passed ≥ Required questions for that phase  
3. GitHub requirements validated = True

### Phase Requirements

The `PHASE_REQUIREMENTS` dictionary in `api/shared/badges.py` defines the exact counts:

```python
PHASE_REQUIREMENTS = {
    0: PhaseRequirements(steps=15, questions=12),  # 6 topics (IT Fundamentals)
    1: PhaseRequirements(steps=36, questions=12),  # 6 topics (CLI, Git, IaC)
    2: PhaseRequirements(steps=30, questions=12),  # 6 topics (Python, APIs)
    3: PhaseRequirements(steps=31, questions=8),   # 4 topics (AI phase)
    4: PhaseRequirements(steps=51, questions=18),  # 9 topics (Cloud deployment)
    5: PhaseRequirements(steps=55, questions=12),  # 6 topics (DevOps)
    6: PhaseRequirements(steps=64, questions=12),  # 6 topics (Security)
}
```

**Important:** These requirements must match the actual content. Use this command to verify:
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

### Badge Tiers

- **Explorer** (Bronze): Phase 0 complete
- **Practitioner** (Silver): Phase 1 complete
- **Builder** (Blue): Phase 2 complete
- **Specialist** (Purple): Phase 3 complete
- **Architect** (Gold): Phase 4 complete
- **Master** (Red): Phase 5 complete
- **Legend** (Rainbow): Phase 6 complete

---

## Database Tables

### StepProgress

Tracks which learning steps a user has completed:
```
- user_id: User's Clerk ID
- topic_id: Topic identifier
- step_order: Which step (1-indexed)
- completed_at: Timestamp
```

### QuestionAttempt

Tracks question attempts and passes:
```
- user_id: User's Clerk ID
- question_id: Question identifier
- is_correct: Boolean
- created_at: Timestamp
```

### GitHubSubmission

Tracks hands-on project submissions:
```
- user_id: User's Clerk ID
- requirement_id: Which requirement
- phase_id: Phase number
- submitted_url: GitHub URL
- is_validated: Boolean
- validated_at: Timestamp
```

### UserActivity

Aggregated daily activity counts (for heatmap):
```
- user_id: User's Clerk ID
- activity_date: Date
- activity_count: Number of activities
```

---

## API Endpoints

### Dashboard

`GET /api/dashboard`

Returns:
```json
{
  "user": {...},
  "phases": [...],
  "overall_progress": 45.5,
  "phases_completed": 3,
  "phases_total": 7,
  "current_phase": 4
}
```

### Public Profile

`GET /api/users/{username}/profile`

Returns:
```json
{
  "username": "...",
  "phases_completed": 3,
  "current_phase": 4,
  "streak": {...},
  "badges": [...],
  "activity_heatmap": {...}
}
```

---

## Frontend Components

### Dashboard Page (`/dashboard`)

Displays:
- Welcome message with streak
- "X of 7 phases completed" progress bar
- Phase cards with individual progress

### Profile Page (`/user/[username]`)

Displays:
- User avatar and info
- Phases completed count
- Best streak
- Earned badges
- Activity heatmap
- GitHub submissions showcase

### Phase Page (`/[phaseSlug]`)

Displays:
- Phase overview and prerequisites
- Topic list (with lock indicators)
- GitHub verification section (when all topics complete)

---

## Streak System

Streaks track consecutive days of activity:

- **Current Streak**: Days in a row with at least 1 activity
- **Longest Streak**: All-time best consecutive days

Activities that count:
- Completing a learning step
- Passing a knowledge question
- Submitting a GitHub verification

The streak resets if no activity is recorded for a calendar day.

---

## Troubleshooting

### Badge Not Showing

1. Verify all steps are completed for the phase
2. Verify all questions are passed for the phase
3. Verify all GitHub requirements are validated
4. Check if the phase has the correct requirements in `PHASE_REQUIREMENTS`

### Topic Locked When It Shouldn't Be

1. Check if the previous topic has ALL steps completed
2. Check if the previous topic has ALL questions passed
3. Verify you're not in a different phase

### Phase Locked When It Shouldn't Be

1. Check if the previous phase has all topics complete
2. Check if the previous phase has all GitHub requirements validated
3. Verify the phase order (phases unlock sequentially 0 → 1 → 2 → ...)

---

## Code References

| Component | File |
|-----------|------|
| Badge computation | `api/shared/badges.py` |
| Profile endpoint | `api/routes/users.py` |
| Progress schemas | `api/shared/schemas.py` |
| Frontend types | `frontend/src/lib/types.ts` |
| Progress calculation | `frontend/src/lib/api.ts` |
| Dashboard UI | `frontend/src/app/dashboard/page.tsx` |
| Profile UI | `frontend/src/app/user/[username]/page.tsx` |
| Phase page | `frontend/src/app/[phaseSlug]/page.tsx` |
