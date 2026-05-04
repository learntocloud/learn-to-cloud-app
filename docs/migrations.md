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

Production uses separate PostgreSQL data-plane principals. The production
cutover to this model is complete; these notes describe the intended steady
state, not a bootstrap procedure.

| Principal | Purpose |
| --- | --- |
| PostgreSQL Entra admin group | Break-glass administration and role management. Configured with `postgres_entra_admin_*` Terraform variables. Do not use this principal for app runtime or normal migrations. |
| API managed identity | Runtime application identity attached to the Container App. It gets the Entra token used for PostgreSQL login. |
| API PostgreSQL role | Runtime database role, `ltc_api_runtime_<environment>` by default. It is mapped to the API managed identity object ID, has DML and sequence privileges, and must not own schema objects. |
| Migration principal | Deploy-time Alembic migrations. It owns application schema objects and runs schema changes. This principal does not need Azure RBAC beyond acquiring a PostgreSQL Entra token. |

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
| `POSTGRES_MIGRATION_USER` | PostgreSQL role name for the mapped migration principal used by Alembic. |

Optional Terraform variable:

| Variable | Purpose |
| --- | --- |
| `postgres_api_runtime_role` | PostgreSQL runtime role used by the API. Defaults to `ltc_api_runtime_<environment>`. |

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
