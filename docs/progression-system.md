# Progression System

## Core Concept

A **Phase is Complete** when ALL requirements are met:
1. All **Learning Steps** are completed.
2. All **Hands-on Requirements** are verified successfully.

This drives: profile stats and dashboard progress.

## Content Access

All phases, topics, and learning steps are unlocked, so learners can read the
curriculum in any order. Hands-on verification is sequential from Phase 4
through Phase 7: each phase's requirements must be verified before submissions
for the next phase unlock.

## Progress Calculation

**Topic:** `Steps Completed / Total Steps`

**Phase:** two separate measures:

- Learning progress: `Completed Steps / Current Catalog Steps`
- Verification progress: `Succeeded Requirements / Current Catalog Requirements`

A phase is complete only when both measures are complete. A measure with no
requirements is complete by definition.

## Key Files

| Purpose | File |
|---------|------|
| Progress | `api/src/learn_to_cloud/services/progress_service.py` |
| Hands-on | `packages/learn-to-cloud-shared/src/learn_to_cloud_shared/requirements.py` |
| Catalog reads | `packages/learn-to-cloud-shared/src/learn_to_cloud_shared/content_service.py` |

## Important

Step/topic counts are **dynamically derived** from content YAML—do NOT hardcode.

Step and requirement completion identity uses stable UUIDs, not positional
order. Progress intersects stored UUIDs with the current catalog so retired
content no longer counts without deleting learner history.
