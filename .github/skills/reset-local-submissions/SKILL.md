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

## Combined Example

```bash
cd <workspace>/api && uv run python scripts/reset_local_submissions.py \
  --user-id <user_id> \
  --requirement-slug devops-implementation \
  --requirement-slug journal-api-implementation
```

## Expected Output

- Matching attempts, each with its user ID, requirement slug, and outcome
- Number of deleted `verification_attempts` rows

## Notes

- The script refuses to run unless the configured database host is a local
  development one (`localhost`, `127.0.0.1`, `::1`, `db`, `postgres`) and Azure
  managed-identity Postgres is not in use.
- Submission state lives in `verification_attempts`; slugs are resolved to
  `requirement_uuid` through the curriculum artifact, so an unknown slug fails
  fast instead of silently deleting nothing.
- Progress is derived live from those attempts on next page load, so no
  denormalized counter needs updating.
