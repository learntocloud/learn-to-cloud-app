# Database Migrations

This project uses [Alembic](https://alembic.sqlalchemy.org/) for database schema migrations.

## How Migrations Run in Production

Migrations run automatically via an **init container** in Azure Container Apps. The init container:

1. Uses the **same Docker image** as the API
2. Executes `python -m alembic upgrade head` before the app container starts
3. Shares the same managed identity and network access as the app — no extra firewall rules needed
4. If the migration fails, the app container **never starts**, preventing traffic from hitting a mismatched schema

This is configured in [`infra/container-apps.tf`](../infra/container-apps.tf) as an `init_container` block.

> **Note:** Because Container Apps may have multiple replicas, Alembic uses a PostgreSQL advisory lock
> (defined in `alembic/env.py`) to ensure only one replica runs migrations at a time.

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
