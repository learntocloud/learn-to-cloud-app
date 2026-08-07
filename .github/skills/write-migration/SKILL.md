---
name: write-migration
description: Write or edit an Alembic migration safely against production data and constraints. Use for migrations, schema constraints, indexes, or column defaults.
---

# Write Migration

Treat any migration merged to a shared branch or applied to an environment as
immutable; correct it with a new migration. An unmerged migration may be
edited when it is known not to have run outside disposable local databases.

Preserve these production-safety rules:

- Drop incompatible check constraints before transforming rows, then recreate
  and validate them.
- Clean or merge existing duplicates before adding uniqueness.
- Set local lock and statement timeouts.
- Build production indexes concurrently inside
  `op.get_context().autocommit_block()`.
- Make upgrades safe for populated databases and write a valid downgrade.
- Keep one Alembic head and follow repository naming/docstring checks.

Inspect adjacent migrations and `api/scripts/lint_migration_sql.py` for current
conventions. Run the migration-specific checks plus `uv run poe check`.
