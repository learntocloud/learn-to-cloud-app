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

The API container sets `RUN_MIGRATIONS_ON_STARTUP=false` in
[`infra/container-apps.tf`](../infra/container-apps.tf). This keeps the runtime
managed identity from needing schema owner or PostgreSQL administrator
privileges.

> **Note:** The migration job runs with one replica, and Alembic also uses a
> PostgreSQL advisory lock (defined in `alembic/env.py`) to guard against
> accidental concurrent executions.

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
| Migration PostgreSQL role | Deploy-time Alembic migration role. It owns application schema objects and runs schema changes. Its name is provided by `POSTGRES_MIGRATION_USER` in GitHub Actions and by `postgres_migration_role` in Terraform. |

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
| `POSTGRES_MIGRATION_USER` | PostgreSQL role name for the mapped migration job identity used by Alembic. The deploy workflow passes this into Terraform as `postgres_migration_role`. |

Terraform variables:

| Variable | Purpose |
| --- | --- |
| `postgres_migration_role` | PostgreSQL migration role used by the Azure Container Apps migration job. Required; set from `POSTGRES_MIGRATION_USER` in GitHub Actions. |
| `postgres_api_runtime_role` | PostgreSQL runtime role used by the API. Defaults to `ltc_api_runtime_<environment>`. |

No GitHub secret is needed for PostgreSQL migration authentication. GitHub only
starts the Azure Container Apps Job; the job uses its own managed identity to
acquire the PostgreSQL Entra token inside Azure.

The migration job identity must be mapped to the migration PostgreSQL role before
the job can connect. Use the Terraform output
`migration_identity_principal_id` when creating or verifying that mapping.

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
