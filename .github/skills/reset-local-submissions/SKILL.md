---
name: reset-local-submissions
description: Undo local submissions for DevOps and Verify Journal API Implementation so you can re-test verification flows. Also supports custom requirement IDs and user scoping.
---

# Reset Local Submissions

Use this skill to remove local submission records and recompute phase counters for testing.

## When to Use

- User says "undo my local submission"
- User wants to re-test hands-on verification
- User asks to reset DevOps or Journal API verification attempts

## Default Reset Targets

The default command resets:
- `devops-implementation`
- `journal-api-implementation`

## Command

```bash
cd <workspace>/api && uv run python scripts/reset_local_submissions.py
```

## Safe Preview (No Changes)

```bash
cd <workspace>/api && uv run python scripts/reset_local_submissions.py --dry-run
```

## Restrict to Specific User

`--user-id` is the **GitHub user ID** (e.g. `6733686` for madebygps), not a sequential DB ID.
Run `--dry-run` first (without `--user-id`) to discover the IDs in your local database.

```bash
cd <workspace>/api && uv run python scripts/reset_local_submissions.py --user-id <github_user_id>
```

## Custom Requirement IDs

```bash
cd <workspace>/api && uv run python scripts/reset_local_submissions.py \
  --requirement-id <requirement_id_1> \
  --requirement-id <requirement_id_2>
```

## Combined Example

```bash
cd <workspace>/api && uv run python scripts/reset_local_submissions.py \
  --user-id <user_id> \
  --requirement-id devops-implementation \
  --requirement-id journal-api-implementation
```

## Expected Output

- Matching rows found and affected user IDs
- Number of deleted submission rows
- Recomputed `user_phase_progress.validated_submissions` per affected phase

## Notes

- This is for local/testing databases only.
- The script updates denormalized progress counts so dashboard progress remains consistent.
