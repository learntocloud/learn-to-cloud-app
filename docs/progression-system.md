# Progression System

## Core Concept

A **Phase is Complete** when ALL requirements are met:
1. ✅ All **Learning Steps** completed
2. ✅ All **Hands-on Requirements** validated

This drives: profile stats and dashboard progress.

## Content Access

All phases, topics, and steps are **fully unlocked** - users can access any content in any order. There is no gating based on completion status.

## Progress Calculation

**Topic:** `Steps Completed / Total Steps`

**Phase:** `(Steps + Hands-on) / Total`

## Badge Tiers

(Badges have been removed from the platform.)

## Key Files

| Purpose | File |
|---------|------|
| Progress | `services/progress_service.py` |
| Hands-on | `services/phase_requirements_service.py` |

## Important

Step/topic counts are **dynamically derived** from content YAML—do NOT hardcode.

Step completion identity is based on stable `step_id` values (not positional order), and
progress is reconciled against currently loaded content to avoid drift after curriculum edits.

---

## Feedback
If you encounter a pattern, convention, or edge case that should be added to these instructions, let me know so we can consider including it.
