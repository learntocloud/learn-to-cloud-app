# Database Migrations

This project uses [Alembic](https://alembic.sqlalchemy.org/) for database schema migrations.

## How Migrations Run in Production

Migrations run in GitHub Actions before the Container App image is updated. The
workflow:

1. Authenticates to Azure with the deploy service principal.
2. Runs `uv run alembic upgrade head` with `POSTGRES_USER` set to the mapped migration principal.
3. Stops the deployment before `az containerapp update` if the migration fails.

The API container sets `RUN_MIGRATIONS_ON_STARTUP=false` in
[`infra/container-apps.tf`](../infra/container-apps.tf). This keeps the runtime
managed identity from needing schema owner or PostgreSQL administrator
privileges.

> **Note:** Because Container Apps may have multiple replicas, Alembic uses a PostgreSQL advisory lock
> (defined in `alembic/env.py`) to ensure only one replica runs migrations at a time.

## Production Database Identities

Production uses separate PostgreSQL data-plane principals:

| Principal | Purpose |
| --- | --- |
| PostgreSQL Entra admin group | Bootstrap, break-glass administration, and role management. Configured with `postgres_entra_admin_*` Terraform variables. |
| API managed identity | Runtime application access only. It must be mapped as a non-admin PostgreSQL Entra principal. |
| Migration principal | Deploy-time Alembic migrations. It owns application schema objects and grants DML privileges to the API role. This principal does not need Azure RBAC. |

### Rollout order

Before merging the Terraform change that removes the API identity as a
PostgreSQL Entra administrator, make sure the dedicated PostgreSQL Entra admin
principal exists and the GitHub repository variables/secrets below are set.

After Terraform switches the server admin to the dedicated admin principal, run
the bootstrap script as that admin before deploying the app with
`RUN_MIGRATIONS_ON_STARTUP=false`. This avoids leaving the runtime API identity
without a mapped non-admin PostgreSQL role.

The one-time identity setup starts with:

```bash
scripts/bootstrap_db_identities.sh
```

The script creates or reuses the PostgreSQL admin group and migration service
principal, configures GitHub Actions OIDC for migrations, sets the repository
variables/secrets below, applies Terraform when requested, and runs the SQL
bootstrap when requested.

For production rollout without local Terraform secrets:

1. Run `scripts/bootstrap_db_identities.sh` to create/reuse identities and set
   GitHub variables/secrets. This sets `DB_IDENTITY_BOOTSTRAPPED=false`, so a
   merge can apply Terraform without running migrations or updating the app.
2. Merge the branch and let GitHub Actions apply Terraform with repository
   secrets.
3. Run `scripts/bootstrap_db_identities.sh --skip-gh --run-sql` locally to map
   and grant the PostgreSQL roles. After SQL succeeds, the script sets
   `DB_IDENTITY_BOOTSTRAPPED=true`.
4. Run the deploy workflow manually to run migrations and update the app.

If you need to run the SQL manually instead:

```bash
API_OBJECT_ID="$(az identity show \
  --resource-group <resource-group-name> \
  --name id-ltc-api-dev \
  --query principalId \
  -o tsv)"

export PGPASSWORD="$(az account get-access-token --resource-type oss-rdbms --query accessToken -o tsv)"

psql "host=<server>.postgres.database.azure.com dbname=postgres sslmode=require user=<admin-group-name>" \
  -v database_name=learntocloud \
  -v api_role=id-ltc-api-dev \
  -v api_object_id="$API_OBJECT_ID" \
  -v migration_role=<migration-principal-name> \
  -v migration_object_id=<migration-principal-object-id> \
  -f infra/postgres-bootstrap.sql
```

The bootstrap script creates the API and migration Entra principals with
`isAdmin=false`, revokes elevated API role flags where present, grants runtime
DML privileges to the API role, and transfers schema object ownership to the
migration role.

Required repository variables for deployment:

| Variable | Purpose |
| --- | --- |
| `POSTGRES_ENTRA_ADMIN_OBJECT_ID` | Object ID for the dedicated PostgreSQL Entra admin group/principal. |
| `POSTGRES_ENTRA_ADMIN_PRINCIPAL_NAME` | Display name for the PostgreSQL Entra admin principal. |
| `POSTGRES_ENTRA_ADMIN_PRINCIPAL_TYPE` | `Group`, `User`, or `ServicePrincipal`; defaults to `Group` in the workflow. |
| `POSTGRES_MIGRATION_USER` | PostgreSQL role name for the mapped migration principal used by Alembic. |
| `DB_IDENTITY_BOOTSTRAPPED` | Deployment gate. Keep `false` until the SQL bootstrap succeeds, then set `true`. |

Required repository secret for migrations:

| Secret | Purpose |
| --- | --- |
| `AZURE_MIGRATION_CLIENT_ID` | Client ID of the migration service principal or managed identity. It is used only to acquire a PostgreSQL Entra token. |

## Running Migrations Locally

### Prerequisites

- PostgreSQL running locally (via `docker compose up db` or a local install)
- API virtual environment set up (`cd api && uv sync`)

### Run All Pending Migrations

```bash
cd api
uv run alembic upgrade head
```

### Create a New Migration

After modifying models in `models.py`:

```bash
cd api
uv run alembic revision --autogenerate -m "short description of change"
```

Review the generated file in `api/alembic/versions/` — autogenerate is not perfect, so always check:
- That it detected the correct changes
- That `upgrade()` and `downgrade()` are both correct
- That no data migrations are needed alongside the schema change

### Rollback One Migration

```bash
cd api
uv run alembic downgrade -1
```

### Check Current Migration State

```bash
cd api
uv run alembic current
```

### View Migration History

```bash
cd api
uv run alembic history --verbose
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
- **Test migrations both ways** — run `upgrade head` then `downgrade -1` then `upgrade head` again locally before pushing.
- **Large data migrations** should be done in a separate migration file from schema changes to keep each migration focused and reversible.
