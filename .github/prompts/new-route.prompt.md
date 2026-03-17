---
name: new-route
description: Scaffold a new feature with Route, Service, and Repository following project conventions.
---

Create a new feature following the **Routes > Services > Repositories** architecture.

## What I need from you

1. **Feature name** and a brief description of what it does.
2. Whether it needs **database access** (new model/table, or existing model).
3. Whether it's a **page route** (TemplateResponse), **HTMX route** (HTMLResponse fragment), or **API route** (JSON).
4. Whether it requires **authentication** (`UserId` or `OptionalUserId`).

## What to generate

### Route (`api/routes/`)
- Add to an existing route file or create a new one with `APIRouter(prefix="...", tags=[...])`.
- Use `async def` for all handlers.
- Use `DbSession` or `DbSessionReadOnly` from `core.database` for database access.
- Use `UserId` or `OptionalUserId` from `core.auth` for authentication.
- Keep routes thin - delegate business logic to the service layer.
- Add a module-level docstring explaining the routes.

### Service (`api/services/`)
- Pure business logic - no `Request`, no HTTP concepts.
- Accept `AsyncSession` as parameter.
- Call repository methods for database access.
- Add logging with structured `extra={}` dicts.

### Repository (`api/repositories/`)
- Database queries only.
- Constructor takes `AsyncSession` as `self.db`.
- **Never commit** - only `flush()`. The caller owns the transaction.
- Return ORM models or primitives.

### Schema (`api/schemas.py`)
- Add Pydantic response/request models if this is an API route.

### Test (`api/tests/`)
- Create unit tests with `@pytest.mark.unit`.
- Mock the repository layer with `autospec=True`.
- Use `AsyncMock()` for async methods.

## Validation
After generating, run: `cd api && uv run ruff check . && uv run ruff format --check . && uv run ty check`
