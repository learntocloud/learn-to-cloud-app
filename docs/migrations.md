# Database Migrations

This project uses [Alembic](https://alembic.sqlalchemy.org/) for database schema migrations.

## How Migrations Run in Production

Migrations run in an Azure Container Apps manual Job before the API Container
App image is updated. The workflow:

1. Builds and pushes the new API image to Azure Container Registry.
2. Starts the migration job with that image tag.
3. The job runs `alembic upgrade head` with `POSTGRES_USER` set to the mapped
   migration PostgreSQL role.
4. The workflow polls the job execution until it succeeds or fails.
5. Stops the deployment before `az containerapp update` if the migration job
   fails.

The API container does not run migrations on startup. This keeps the runtime
managed identity from needing schema owner or PostgreSQL administrator
privileges, and lets the migration runner stay tiny — single process, no
multi-worker race to defend against.

> **Single-runner guarantee.** The migration Container App Job is configured
> with `parallelism = 1`, `replica_completion_count = 1`, and
> `replica_retry_limit = 0` (`infra/migrations.tf`). Exactly one process
> ever executes `alembic upgrade head` per deploy. `alembic/env.py` relies
> on this and does not include application-layer concurrency controls.

Terraform keeps the migration job shape, but it does not manage rollout tags.
To satisfy Azure's create-time image requirement, Terraform creates the job with
`mcr.microsoft.com/k8se/quickstart:latest` as a placeholder image and ignores
future image changes. On each deploy, the workflow starts the job with the real
`migrations:<commit-sha>` image.

### Failure Detection

`alembic/env.py` logs and re-raises every exception from
`context.run_migrations()`. `api/scripts/run_migrations.py` then verifies the
current heads with `command.current(config, check_heads=True)` and runs
`command.check(config)` to compare the physical schema with model metadata.
Any failure makes the migration job exit non-zero and stops the deploy.

This guards against the class of bug from issue #432, where an earlier
version of `env.py` substring-matched `"duplicate"` / `"already exists"`
in failure messages and swallowed real `UniqueViolation`s as "already
applied by another process." Production stayed pinned to an older
revision for eight days while CI reported green deploys.

## Display-name rollout (#836)

Ship the schema addition and application cutover together, then remove legacy
storage in a separate cleanup release. Merging requires separate authorization.

| Release | Database | Application |
| --- | --- | --- |
| Profile release (`0058_add_user_display_name`) | Adds nullable `users.display_name` as unrestricted `Text`, with no default, index, or uniqueness constraint; retains both legacy columns | Uses `display_name` for profiles and greetings |
| Cleanup (later PR) | Removes `first_name` and `last_name` | Removes legacy model metadata and temporary mapper exclusions |

Deployment applies the migration and checks schema agreement before starting
the new API image. `display_name` is a normal mapped attribute; the new app
requires the expanded schema. Old instances continue to use the retained legacy
columns until replaced. There is no separate schema-only deployment.

Legacy columns remain in table metadata but are excluded from the new ORM
mapping, so runtime queries and writes no longer need them. This keeps strict
migration schema comparison intact and prepares the app for later cleanup.
Remove that transitional metadata only with the cleanup migration.

The profile release's PostgreSQL compatibility tests execute normal ORM insertion, SELECTs, both
entity-returning repository paths, conflict fallback, batch lookups, refresh,
clearing, and deletion with progress cascades. They cover expanded storage and
a manually contracted disposable database while legacy metadata is retained;
they do not require the future cleanup migration. The deployed profile schema must
still retain all three columns to pass strict migration metadata comparison.

Expansion backfills once. Each legacy component containing non-whitespace text
is preserved exactly, and populated components are joined with one space.
Both absent or blank components produce SQL `NULL`. Blank detection explicitly
handles ASCII whitespace and separators and Unicode whitespace, including
nonbreaking spaces; it does not depend on the database locale. Stored outer
and repeated internal spaces, Unicode, and names longer than 255 characters
are preserved. This is best-effort recovery: information lost by the old name
parser cannot be recreated. IDs, usernames, legacy values, timestamps,
permissions, and progress ownership are not changed.

The column addition and backfill share one transaction with a local 5-second
lock timeout and 2-minute per-statement timeout. Rehearse against representative
disposable data and assess aggregate account counts before deployment. If the
backfill cannot fit this bounded operation, revisit batching rather than
removing the timeouts. No production names need to be inspected or logged.

An old revision can still write legacy fields after backfill. That accepted gap
can leave an older name or username greeting until a login through the new app refreshes
the profile. Do not add a trigger, dual write, legacy read fallback, or another
`WHERE display_name IS NULL` backfill: NULL may be an intentional name removal
after cutover.

### Deployment gates and recovery

- **Profile release:** after an authorized merge, wait for the entire
  Application Deploy workflow (`app-deploy.yml`) to succeed. Confirm the
  expanded schema, expected API image, and verification Functions deployment.
  Run authenticated profile/dashboard, readiness, and verification-submit
  checks. All old API replicas must retire, with no rollback outstanding,
  before cleanup may merge. A passing `/ready` alone does not prove that old
  readers are gone; revision drift is warning-only.
- **Cleanup:** after a separately authorized merge, require the full deployment plus
  authenticated profile/dashboard and public community checks.

Downgrading the addition drops `display_name` and loses any refreshed canonical
names; legacy columns remain unchanged. The new app must not be running during
that downgrade. Reapplying the addition reconstructs only the old legacy values,
not discarded display names. Cleanup's future downgrade restores empty nullable legacy columns,
not their discarded contents, and must not split the canonical name.

After cleanup, pre-cutover code is not an allowed image-only rollback. Prefer a
forward fix. Even if the profile release's runtime supports the contracted table,
its older migration files do not know the cleanup revision and its metadata still expects legacy
columns. Any compatible image-only recovery must retain schema-aware migration
tooling and account for revision-drift warnings; do not rerun an old deployment
workflow as an assumed rollback.

Use a disposable database matching the checked-out release for local reviews.
Before switching from cleanup to an earlier branch, downgrade that disposable database
using cleanup's migration files or create a fresh disposable database. Never reset
normal development data. Upper stacked PRs targeting another feature branch
have local checks only under the current CI policy; require normal successful
PR CI after each layer is retargeted to `main`.

## Production Database Identities

Production uses separate PostgreSQL data-plane principals. The production
cutover to this model is complete; these notes describe the intended steady
state, not a bootstrap procedure.

| Principal | Purpose |
| --- | --- |
| PostgreSQL Entra admin group | Break-glass administration and role management. Configured with `postgres_entra_admin_*` Terraform variables. Do not use this principal for app runtime or normal migrations. |
| API managed identity | Runtime application identity attached to the API Container App. It gets the Entra token used for runtime PostgreSQL login. |
| API PostgreSQL role | Runtime database role, `ltc_api_runtime_<environment>` by default. It is mapped to the API managed identity object ID, has DML and sequence privileges, and must not own schema objects. |
| Migration job managed identity | User-assigned identity attached to the Container Apps migration job. It pulls the API image from ACR and gets the Entra token used by Alembic. |
| Migration PostgreSQL role | Deploy-time Alembic migration role. It owns application schema objects and runs schema changes. Terraform defaults the name to `ltc-postgres-migrations-<environment>` and exposes the effective name as `migration_postgres_role`. |

Do not make the API managed identity a PostgreSQL Flexible Server Entra admin.
Azure removes a PostgreSQL Entra admin by attempting to drop the mapped database
role. If the API runtime role is also a server admin, removing that admin can
break the runtime role or fail because database objects, grants, or default ACLs
still depend on it. Keep the Azure managed identity name and PostgreSQL role name
distinct so it is clear which object lives in Azure and which object lives in
PostgreSQL.

Required repository variables for deployment:

| Variable | Purpose |
| --- | --- |
| `POSTGRES_ENTRA_ADMIN_OBJECT_ID` | Object ID for the dedicated PostgreSQL Entra admin group/principal. |
| `POSTGRES_ENTRA_ADMIN_PRINCIPAL_NAME` | Display name for the PostgreSQL Entra admin principal. |
| `POSTGRES_ENTRA_ADMIN_PRINCIPAL_TYPE` | `Group`, `User`, or `ServicePrincipal`; defaults to `Group` in the workflow. |

Terraform variables:

| Variable | Purpose |
| --- | --- |
| `postgres_migration_role` | Optional PostgreSQL migration role override. Defaults to `ltc-postgres-migrations-<environment>`. |
| `postgres_api_runtime_role` | PostgreSQL runtime role used by the API. Defaults to `ltc_api_runtime_<environment>`. |

No GitHub secret is needed for PostgreSQL migration authentication. GitHub only
starts the Azure Container Apps Job; the job uses its own managed identity to
acquire the PostgreSQL Entra token inside Azure.

The migration job identity must be mapped to the effective migration PostgreSQL
role before the job can connect. Use Terraform outputs
`migration_identity_principal_id` and `migration_postgres_role` when creating or
verifying that mapping.

## Running Migrations Locally

### Prerequisites

- PostgreSQL running locally (via `docker compose up db` or a local install)
- Python workspace set up (`uv sync --all-packages --locked` from the repo root)

### Run All Pending Migrations

```bash
cd api && uv run alembic upgrade head
```

### Create a New Migration

After modifying models in `models.py`:

```bash
cd api && uv run alembic revision --autogenerate -m "short description of change"
```

Review the generated file in `api/alembic/versions/` — autogenerate is not perfect, so always check:
- That it detected the correct changes
- That `upgrade()` and `downgrade()` are both correct
- That no data migrations are needed alongside the schema change

### Rollback One Migration

```bash
cd api && uv run alembic downgrade -1
```

### Check Current Migration State

```bash
cd api && uv run alembic current
```

### View Migration History

```bash
cd api && uv run alembic history --verbose
```

## Using the Compose database

Compose runs the local PostgreSQL dependency. Run migrations and the API
directly from the Python workspace:

```bash
# Start the database
docker compose up db -d

# Run migrations against the Compose database
cd api
uv run alembic upgrade head

# Start the API
uv run python -m uvicorn learn_to_cloud.main:app --reload --port 8000
```

## Tips

- **Never edit a migration that's already been applied in production.** Create a new migration instead.
- **Test migrations both ways** -- run `upgrade head` then `downgrade -1` then `upgrade head` again locally before pushing.
- **Large data migrations** should be done in a separate migration file from schema changes to keep each migration focused and reversible.
- **When adding a unique index or constraint**, always clean up duplicate rows first in the same migration. CI runs against an empty database, so it won't catch constraint violations that only happen with real data.

## Migration Tests

The project uses [pytest-alembic](https://pytest-alembic.readthedocs.io/) for
automated migration testing. Tests live in `api/tests/test_migration_chain.py`
and run against a dedicated `test_alembic_migrations` database (separate from
the main test database).

### What the tests check

| Test | What it does |
| --- | --- |
| `test_upgrade` | Runs every migration from base to head, one at a time |
| `test_single_head_revision` | Makes sure the migration chain has no forks |
| `test_model_definitions_match_ddl` | Checks that SQLAlchemy models match the actual database schema |
| `test_up_down_consistency` | Upgrades then downgrades each migration to make sure both directions work |

### How it works

pytest-alembic passes a database engine into `alembic/env.py` via
`config.attributes["connection"]`. The `run_migrations_online()` function
uses that engine instead of creating its own. This lets the test framework
control which database gets used.

### Running migration tests

```bash
cd api && uv run pytest tests/test_migration_chain.py -v
```

These tests are included in the standard `uv run pytest tests/` run.

## SQL Linting with Squawk

New migrations are automatically linted with
[Squawk](https://squawkhq.com/) in CI. Squawk checks the generated SQL
for unsafe Postgres patterns like:

- Creating indexes without `CONCURRENTLY` (blocks writes)
- Adding constraints without `NOT VALID` (blocks reads/writes during scan)
- Missing `lock_timeout` / `statement_timeout` settings
- Dropping tables or columns (breaks existing clients)

### How it works

The script `api/scripts/lint_migration_sql.py` finds migration files
added in the PR (compared to `origin/main`), generates the SQL each
migration would run via `alembic upgrade --sql`, and feeds it to squawk.

Configuration lives in `api/.squawk.toml`.

### Running locally

```bash
cd api && uv run python scripts/lint_migration_sql.py
```

This only checks new migrations (files added vs `origin/main`). If
you're working on a branch with no new migrations, it exits cleanly.

## Curriculum tables and the concurrent-friendly patterns

Phases B through D of the curriculum refactor (#461) introduced
patterns this repo now uses as a default for any non-trivial
migration. They show up across `0028_step_progress_cleanup.py`,
`0029_submissions_uuid_fk.py`, and `0030_verification_jobs_uuid_fk.py`
if you need a worked example.

### Standard preamble

```python
def upgrade() -> None:
    op.execute("SET LOCAL lock_timeout = '5s'")
    op.execute("SET LOCAL statement_timeout = '2min'")
```

`lock_timeout` bounds how long any one statement waits for a lock
before failing the deploy loudly. `statement_timeout` bounds total
statement runtime.

### `NOT NULL` without a long write lock

Postgres's naive `ALTER TABLE ... SET NOT NULL` takes
`ACCESS EXCLUSIVE` and scans the table to prove no NULLs exist. The
safer pattern:

```python
# 1. Add a CHECK constraint NOT VALID -- fast, metadata-only.
op.execute("""
    DO $$ BEGIN
      IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'ck_foo_x_nn') THEN
        ALTER TABLE foo ADD CONSTRAINT ck_foo_x_nn CHECK (x IS NOT NULL) NOT VALID;
      END IF;
    END $$;
""")

# 2. VALIDATE in its own transaction. Runs under SHARE UPDATE EXCLUSIVE
#    so reads + writes keep flowing.
with op.get_context().autocommit_block():
    op.execute("""
        DO $$ BEGIN
          IF EXISTS (
            SELECT 1 FROM pg_constraint
            WHERE conname = 'ck_foo_x_nn' AND NOT convalidated
          ) THEN
            ALTER TABLE foo VALIDATE CONSTRAINT ck_foo_x_nn;
          END IF;
        END $$;
    """)

# 3. SET NOT NULL is now a metadata flip -- postgres uses the
#    validated CHECK to skip the scan.
op.alter_column("foo", "x", nullable=False)

# 4. Drop the now-redundant CHECK.
op.execute("ALTER TABLE foo DROP CONSTRAINT IF EXISTS ck_foo_x_nn")
```

### Foreign keys without a long write lock

Same idea — `ADD CONSTRAINT ... NOT VALID` in one transaction, then
`VALIDATE CONSTRAINT` in a separate transaction so the validation scan
runs under the weaker lock:

```python
op.execute("""
    DO $$ BEGIN
      IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'fk_x') THEN
        ALTER TABLE foo
          ADD CONSTRAINT fk_x FOREIGN KEY (x) REFERENCES bar(id)
          ON DELETE RESTRICT NOT VALID;
      END IF;
    END $$;
""")

with op.get_context().autocommit_block():
    op.execute("""
        DO $$ BEGIN
          IF EXISTS (
            SELECT 1 FROM pg_constraint
            WHERE conname = 'fk_x' AND NOT convalidated
          ) THEN
            ALTER TABLE foo VALIDATE CONSTRAINT fk_x;
          END IF;
        END $$;
    """)
```

### Indexes and unique constraints, concurrently

```python
with op.get_context().autocommit_block():
    op.execute("""
        CREATE UNIQUE INDEX CONCURRENTLY IF NOT EXISTS uq_foo_x
            ON foo (x)
    """)
op.execute("""
    DO $$ BEGIN
      IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'uq_foo_x') THEN
        ALTER TABLE foo ADD CONSTRAINT uq_foo_x UNIQUE USING INDEX uq_foo_x;
      END IF;
    END $$;
""")
```

The `IF NOT EXISTS` / `convalidated` / `pg_constraint` checks make the
operation idempotent so a partial-failure retry succeeds.

### Squawk exclusions

`api/.squawk.toml` excludes a few rules globally with documented
reasons. The big ones for the curriculum migrations:

- `ban-drop-column` — curriculum refactor explicitly accepts a brief
  500s window during pod rollover while old pods still reference
  dropped columns. Documented per-migration in the migration's
  docstring.
- `adding-not-nullable-field` — `SET NOT NULL` is in fact safe when
  preceded by a validated `CHECK (col IS NOT NULL)` constraint
  (squawk's static checker can't see the prior CHECK).
