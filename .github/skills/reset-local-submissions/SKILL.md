---
name: reset-local-submissions
description: Undo local submissions for DevOps and Verify Journal API Implementation so you can re-test verification flows. Also supports custom requirement slugs and user scoping. Use when user says "reset local submissions", "undo local verification", "reset phase X locally", or "let me re-test verification".
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

## Custom Requirement Slugs

A requirement slug is the human-friendly identifier such as
`devops-implementation` or `journal-api-implementation`.

```bash
cd <workspace>/api && uv run python scripts/reset_local_submissions.py \
  --requirement-slug <requirement_slug_1> \
  --requirement-slug <requirement_slug_2>
```

The older `--requirement-id` flag still works as a deprecated alias, but it
prints a warning. Prefer `--requirement-slug`.

## Combined Example

```bash
cd <workspace>/api && uv run python scripts/reset_local_submissions.py \
  --user-id <user_id> \
  --requirement-slug devops-implementation \
  --requirement-slug journal-api-implementation
```

## Expected Output

- Matching rows found and affected user IDs
- Number of deleted submission rows

## Notes

- This is for local/testing databases only.
- Progress is derived live from the submissions table on next page load,
  so no denormalized counter needs updating.
