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
`context.run_migrations()`, then verifies the schema actually advanced by
comparing `MigrationContext.get_current_heads()` to
`ScriptDirectory.get_heads()` on the same connection. If they diverge, it
raises and the migration job exits non-zero, failing the deploy.

This guards against the class of bug from issue #432, where an earlier
version of `env.py` substring-matched `"duplicate"` / `"already exists"`
in failure messages and swallowed real `UniqueViolation`s as "already
applied by another process." Production stayed pinned to an older
revision for eight days while CI reported green deploys.

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

## Using docker compose

When running the full stack with `docker compose up`, you need to run migrations manually since they no longer auto-run on startup:

```bash
# Start the database
docker compose up db -d

# Run migrations against the compose database
docker compose run --rm api-multiworker python -m alembic upgrade head

# Then start the API
docker compose up api-multiworker
```

Alternatively, create a one-off migration service in `docker-compose.yml` (see below).

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

## Curriculum content sync

The curriculum tables (`phases`, `topics`, `steps`,
`learning_objectives`, `requirements`) are populated by a separate
sync step on every deploy. See
[`docs/curriculum.md`](./curriculum.md) for the full flow. The
short version:

1. Migrations job runs `alembic upgrade head` and the usual checks.
2. Same job then runs
   `python -m learn_to_cloud_shared.cli.sync_curriculum`, which
   upserts curriculum rows from packaged YAML.
3. Sync soft-deletes (sets `deleted_at`) rather than hard-deletes
   curriculum rows so user state FK references stay valid.

Schema changes to curriculum tables are normal Alembic migrations;
content changes go through the YAML sync.
