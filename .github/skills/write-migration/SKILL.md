---
name: write-migration
description: Write or edit an Alembic database migration safely against production data and constraints. Use when the user says "create a migration", "add a migration", "edit the migration", or asks to change check constraints, unique indexes, or column defaults in the database schema.
---

# Write Migration

Alembic migrations are immutable historical records. **Never edit a migration file after it has been created** — it may have already run in production. If a migration needs correcting, create a new migration instead.

## Check Constraints

When a migration updates row values AND modifies check constraints, always drop the constraints first, then update rows, then add new constraints. Postgres enforces check constraints during the `UPDATE`, so updating rows before dropping the old constraint fails if the new value isn't in the old constraint's allowed list.

## Unique Indexes and Constraints

When a migration adds a unique index or unique constraint, always clean up existing rows that would violate it first, in the same migration. Production databases have data that CI's empty test database does not. Delete or merge duplicate rows before creating the constraint.

## Lint and Timeouts

New migrations are squawk-linted in CI (`api/scripts/lint_migration_sql.py`). Set `SET LOCAL lock_timeout` / `statement_timeout` at the top of the migration, and build indexes with `CREATE INDEX CONCURRENTLY` inside `op.get_context().autocommit_block()`.

Long SQL or string literals in migrations must respect `line-length = 88`. Break long `SELECT` / `INSERT` lists across multiple lines inside the SQL string, because ruff lints the Python source, not the SQL.
