# Database Migrations

Use Alembic migrations for schema changes. Keep model metadata and the migrated
schema in agreement; do not hide drift or suppress migration failures.

## Combine compatible schema and application changes

An additive migration and the application code using it can ship together.
Deployment migrates and checks schema agreement before updating the API image.
The old application still serves traffic while migrations run, so it must remain
compatible with the expanded schema. Remove obsolete columns only after old
instances and rollback requirements have been accounted for.

Brief downtime is acceptable, but the deployment workflow does not stop old
instances before migrating. For an incompatible change, explicitly plan that
stop or use compatible intermediate releases. Do not drop data or weaken
deployment checks merely to combine releases.

## Safety rules

- Treat shared migrations as immutable. If merged to a shared branch or applied
  outside disposable local databases, correct them with a new revision. Edit an
  unmerged migration only when it is known not to have run elsewhere.
- Keep one Alembic head and follow adjacent migrations' naming and docstring
  conventions.
- Bound lock waits and statement execution. If representative data cannot fit
  the bounds, redesign or batch the operation rather than remove the timeouts.
- Test populated-data upgrades and downgrade behavior, including data loss.
  Empty-database upgrades cannot establish compatibility with existing rows.
- Drop incompatible check constraints before transforming rows, then recreate
  and validate them. Before adding uniqueness, detect existing duplicates and
  decide how to resolve them without silently discarding learner data.
- Use a disposable database for upgrade/downgrade rehearsals. Never reset normal
  development data to make an older branch work.

## Concurrent-friendly patterns

For non-trivial migrations, start with bounded timeouts, commonly five seconds
for locks and two minutes for statements. Concurrent index work needs its own
reviewed limits.

To add a `NOT NULL` constraint without a long exclusive scan, add a temporary
`CHECK (column IS NOT NULL) NOT VALID`, validate it in a separate transaction,
then set `NOT NULL` and remove the temporary check. Foreign keys can use the same
add-then-validate pattern.

Build large indexes with `CREATE INDEX CONCURRENTLY` outside a transaction.
A failed build can leave an invalid index: `IF NOT EXISTS` alone does not make
retry safe. Account for that state before attaching a unique constraint.
Keep table creation and its revision stamp atomic; separate concurrent work
when it would otherwise force an early commit.

Use the
[`existing migrations`](https://github.com/learntocloud/learn-to-cloud-app/tree/main/api/alembic/versions)
as worked examples and review transaction boundaries explicitly.
[`0061_auth_sessions_concurrent_indexes`](https://github.com/learntocloud/learn-to-cloud-app/blob/main/api/alembic/versions/0061_auth_sessions_concurrent_indexes.py)
demonstrates bounded concurrent index rebuilding after interruption.

## How Migrations Run in Production

The
[`deployment workflow`](https://github.com/learntocloud/learn-to-cloud-app/blob/main/.github/workflows/app-deploy.yml)
starts a single-runner Container Apps migration job with an immutable image tag.
The API does not migrate on startup. The job applies migrations, verifies the
head, and checks the physical schema against model metadata. Any failure must
stop the API update.

The runner and job configuration are authoritative:
[`run_migrations.py`](https://github.com/learntocloud/learn-to-cloud-app/blob/main/api/scripts/run_migrations.py)
and
[`infra/migrations.tf`](https://github.com/learntocloud/learn-to-cloud-app/blob/main/infra/migrations.tf).
Do not start overlapping migration executions or add automatic retries around
an operation whose partial state has not been reviewed.

## Production Database Identities

Keep three responsibilities separate: break-glass administration, schema-owning
migrations, and application DML. The API runtime role must not own schema objects
or act as the PostgreSQL Entra administrator.

Managed identities and PostgreSQL roles are different objects. Removing a server
administrator can attempt to drop its mapped database role, so do not reuse
the application runtime principal as the server administrator.
The migration job obtains its own Entra token; its identity must be mapped to
the effective migration role before it can connect.

Use Terraform's effective role/identity outputs rather than guessing names.
Configuration lives in
[`infra/database.tf`](https://github.com/learntocloud/learn-to-cloud-app/blob/main/infra/database.tf),
[`variables.tf`](https://github.com/learntocloud/learn-to-cloud-app/blob/main/infra/variables.tf),
and
[`outputs.tf`](https://github.com/learntocloud/learn-to-cloud-app/blob/main/infra/outputs.tf).
New tables also need the API's intended grants; testing as a database owner
does not prove runtime-role access.

## Running Migrations Locally

Start the local database and install the workspace using
[Contributing](contributing.html). From `api/`:

```bash
uv run alembic upgrade head
uv run alembic current
uv run alembic history --verbose
```

After changing models, generate a revision and review both directions:

```bash
uv run alembic revision --autogenerate -m "short description of change"
```

Autogeneration does not decide data transformations, compatibility, safe locking,
or grants for you.

## Migration Tests

Run from `api/` against a local environment:

```bash
uv run python scripts/check_migration_naming.py
uv run python scripts/lint_migration_sql.py
uv run pytest tests/test_migration_chain.py
```

The SQL lint checks migrations added relative to `origin/main`; it does not
review modified historical migrations. Its exclusions and rationale live in
[`.squawk.toml`](https://github.com/learntocloud/learn-to-cloud-app/blob/main/api/.squawk.toml).
A clean lint result is not approval of every operation.

The migration suite recreates its dedicated `test_alembic_migrations` database.
It covers the chain, head, model/schema agreement, and selected populated-data
cases. Add representative data and runtime-role coverage for your change.
Rehearse `upgrade head`, `downgrade -1`, and `upgrade head` again on a disposable
database when the downgrade is supported. Run the full
[quality gate](contributing.html#quality-gates) before pushing.

## Recovery

Prefer a forward fix. Never manually stamp a failed migration or suppress its
error to unblock deployment. Investigate locks, grants, and partial concurrent
indexes before authorizing another attempt.

An image-only rollback is safe only if the older application, migration tooling,
and model metadata understand the current schema. `/ready` warns about revision
drift; it does not prove rollback compatibility or that old replicas retired.
Do not restore legacy identity-cookie authentication: it would undo session
revocation guarantees.

Schema downgrade is not data recovery. Dropping sessions loses logins; recreating
removed profile columns cannot restore their old values. Consult the relevant
migration's `downgrade()` and populated-data tests before choosing recovery.
Historical rollout details belong in migration source and version history,
not in the normal deployment procedure.
