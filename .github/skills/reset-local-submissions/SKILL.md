---
name: reset-local-submissions
description: Reset local verification attempts so verification flows can be retested. Supports requirement slugs and user scoping. Use for "reset local submissions", "undo local verification", or "let me re-test verification".
---

# Reset Local Submissions

Run the guarded script from `api/`:

```bash
uv run python scripts/reset_local_submissions.py
uv run python scripts/reset_local_submissions.py --user-id <github-user-id>
```

The script previews matches and asks for confirmation before deleting them.
For selected requirements or agent-driven use:

```bash
uv run python scripts/reset_local_submissions.py --dry-run
uv run python scripts/reset_local_submissions.py --yes [options]
```

Without filters, the script resets every requirement for every local user.
Filter options are repeatable:

```text
--user-id <github-user-id>
--requirement-slug <slug>
```

Always run with `--dry-run` first and summarize the matched users,
requirements, and outcomes. Ask for confirmation before running with `--yes`.

The script resolves slugs through the curriculum artifact and deletes matching
`verification_attempts`. It refuses non-local databases. Do not bypass that
guard or substitute ad-hoc SQL.
