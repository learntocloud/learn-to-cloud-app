---
name: reset-local-submissions
description: Reset local verification attempts so verification flows can be retested. Supports requirement slugs and user scoping. Use for "reset local submissions", "undo local verification", or "let me re-test verification".
---

# Reset Local Submissions

Use the guarded repository script from `api/`:

```bash
uv run python scripts/reset_local_submissions.py --dry-run
uv run python scripts/reset_local_submissions.py [options]
```

The defaults are `devops-implementation` and
`journal-api-implementation`. Options are repeatable:

```text
--user-id <github-user-id>
--requirement-slug <slug>
```

Always preview first and summarize the matched users, requirements, and
outcomes. Ask for confirmation before running without `--dry-run`.

The script resolves slugs through the curriculum artifact and deletes matching
`verification_attempts`. It refuses non-local databases. Do not bypass that
guard or substitute ad-hoc SQL.
