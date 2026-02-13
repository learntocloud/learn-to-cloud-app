# Progression System

## Core Concept

A **Phase is Complete** when ALL requirements are met:
1. ✅ All **Learning Steps** completed
2. ✅ All **Hands-on Requirements** validated

This drives: badges, profile stats, and certificates.

## Content Access

All phases, topics, and steps are **fully unlocked** - users can access any content in any order. There is no gating based on completion status.

## Progress Calculation

**Topic:** `Steps Completed / Total Steps`

**Phase:** `(Steps + Hands-on) / Total`

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

Step/topic counts are **dynamically derived** from content YAML—do NOT hardcode.

Step completion identity is based on stable `step_id` values (not positional order), and
progress is reconciled against currently loaded content to avoid drift after curriculum edits.

---

## Feedback
If you encounter a pattern, convention, or edge case that should be added to these instructions, let me know so we can consider including it.
