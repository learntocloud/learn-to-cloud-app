---
name: reset-prod-submissions
description: Reset a user's production verification attempts after preview and explicit confirmation. Use for "reset prod submissions", "undo prod verification", or "reset prod for <username>".
---

# Reset Production Submissions

This is a destructive production operation. Use the connection procedure and
firewall cleanup rules from `query-prod-db`.

1. Resolve the GitHub username through `users`; do not use remembered IDs.
2. Resolve any requested requirement slug to its UUID from the current
   curriculum artifact.
3. Preview matching rows from `verification_attempts`, including `id`,
   `requirement_uuid`, `outcome`, and timestamps. Scope by `user_id` and,
   unless resetting everything was explicit, `requirement_uuid`.
4. Show the exact count and scope, then obtain explicit user confirmation.
5. Delete only the previewed scope in one transaction using the same predicates.
   Use `RETURNING id` and verify the remaining count before commit.
6. Re-query after commit and report the deleted and remaining counts.

Progress is derived from `verification_attempts`; no counter requires updating.
Do not use the retired `submissions` or `verification_jobs` tables. Do not
broaden a requirement-scoped reset to all attempts. If the schema, username, or
slug cannot be resolved unambiguously, stop without deleting.
