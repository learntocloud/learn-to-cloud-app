# Progression System

## Core Concept

A **Phase is Complete** when ALL three requirements are met:
1. ✅ All **Learning Steps** completed
2. ✅ All **Knowledge Questions** passed
3. ✅ All **Hands-on Requirements** validated

This drives: badges, unlocking, profile stats, and certificates.

## Unlocking Rules

| Content | Rule |
|---------|---------|
| Phase 0 | Always unlocked |
| Phases 1-6 | Previous phase complete |
| First topic | Always unlocked |
| Subsequent topics | Previous topic complete |
| Admin users | Bypass all locks |

## Progress Calculation

**Topic:** `(Steps + Questions) / Total`

**Phase:** `(Steps + Questions + Hands-on) / Total`

## Badge Tiers

Phase 0→6: Explorer (Bronze) → Practitioner (Silver) → Builder (Blue) → Specialist (Purple) → Architect (Gold) → Master (Red) → Legend (Rainbow)

## Key Files

| Purpose | File |
|---------|------|
| Progress | `services/progress_service.py` |
| Hands-on | `services/phase_requirements_service.py` |
| Badges | `services/badges_service.py` |
| Certificates | `services/certificates_service.py` |

## Important

Step/question counts are **dynamically derived** from content JSON—do NOT hardcode.

---

## Feedback
If you encounter a pattern, convention, or edge case that should be added to these instructions, let me know so we can consider including it.
