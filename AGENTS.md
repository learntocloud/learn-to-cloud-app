# Project Guidelines

## Tech Stack

- **Backend**: FastAPI 0.115 + Python 3.13, async throughout
- **Database**: PostgreSQL 16 via async SQLAlchemy 2.0 + asyncpg, Alembic migrations
- **Frontend**: Jinja2 templates + HTMX + Tailwind CSS v4 + Alpine.js
- **Auth**: GitHub OAuth via Authlib, Azure Managed Identity in prod
- **Observability**: Azure Monitor OpenTelemetry
- **Infra**: Azure Container Apps, Terraform

## Architecture

```
Routes (HTTP) → Services (Business Logic) → Repositories (Database)
```

- Routes handle HTTP concerns, dependency injection, and template rendering
- Services contain business rules — no HTTP knowledge
- Repositories execute queries — return ORM models or primitives

## Code Style

- Ruff for linting + formatting (line-length 88, target py313)
- ty for type checking
- Strict typing with `Mapped[]` and `mapped_column()` — no `Any` unless unavoidable
- Async/await everywhere — no sync database calls

## Build and Test

- **Virtual environment** lives in `api/.venv` (next to `pyproject.toml`, not in repo root)

```bash
# Install
cd api && uv sync

# Lint, format, type-check
ruff check . && ruff format --check . && ty check

# Pre-commit (all checks)
prek run --all-files

# Tests
pytest                         # all tests
pytest -m unit                 # unit only
pytest -m integration          # integration only

# Run locally
docker compose up              # full stack with DB
uv run uvicorn main:app --host 127.0.0.1 --port 8000  # API only (from api/)
```

## Conventions

- Tests use transactional rollback for isolation — no table recreation per test
- `@pytest.mark.unit` / `@pytest.mark.integration` markers are required
- Async test fixtures use `@pytest_asyncio.fixture`; `asyncio_mode = auto`
- Database models use `TimestampMixin` for `created_at`/`updated_at`
- Enums: `class MyEnum(str, PyEnum)` with `native_enum=False` in columns
- Config via `pydantic-settings` (`Settings` class in `core/config.py`)
- Migrations run as subprocess in lifespan to avoid asyncio/psycopg2 deadlock
