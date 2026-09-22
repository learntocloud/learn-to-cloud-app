---
name: write-migration
description: Write or edit an Alembic migration safely against production data and constraints. Use for migrations, schema constraints, indexes, or column defaults.
---

# Write Migration

1. Read [the migration guide](../../../docs/migrations.md), including its safety
   rules, and inspect adjacent migrations and `api/scripts/lint_migration_sql.py`.
2. Determine whether this requires a new revision or whether the existing
   revision is still safe to edit under the guide's immutability rules.
3. Write the migration and add coverage for populated-data upgrades and the
   downgrade behavior, following the documented concurrent-friendly patterns.
4. Run the migration SQL lint and relevant migration tests from the guide.
   Follow [Quality Gates](../../../docs/contributing.md#quality-gates) for the
   full pre-push gate.
