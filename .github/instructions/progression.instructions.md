---
applyTo: "api/services/progress*.py, api/services/badges*.py, api/services/certificates*.py, api/services/phase_requirements*.py, api/services/steps*.py, api/services/questions*.py, api/repositories/progress*.py"
description: "Phase completion logic, badge awards, unlocking rules, and progress calculation"
---

# Progression System

## Core Concept

A **Phase is Complete** when ALL three requirements are met:
1. ✅ All **Learning Steps** completed
2. ✅ All **Knowledge Questions** passed
3. ✅ All **Hands-on Requirements** validated

This drives: badges, unlocking, profile stats, and certificates.

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

**Topic Progress:** `(Steps Completed + Questions Passed) / (Total Steps + Total Questions)`

**Phase Progress:** `(Steps + Questions + Hands-on) / (Total Steps + Total Questions + Total Hands-on)`

## Badge System

| Phase | Badge | Tier |
|-------|-------|------|
| 0 | Explorer | Bronze |
| 1 | Practitioner | Silver |
| 2 | Builder | Blue |
| 3 | Specialist | Purple |
| 4 | Architect | Gold |
| 5 | Master | Red |
| 6 | Legend | Rainbow |

## Key Files

| Purpose | File |
|---------|------|
| Progress calculation | `api/services/progress_service.py` |
| Hands-on requirements | `api/services/phase_requirements_service.py` |
| Badge computation | `api/services/badges_service.py` |
| Certificate eligibility | `api/services/certificates_service.py` |
| Verification types | `api/models.py` (SubmissionType enum) |

## Important

- Steps/questions counts are **dynamically derived** from content JSON at startup
- Do NOT hardcode phase requirement counts
