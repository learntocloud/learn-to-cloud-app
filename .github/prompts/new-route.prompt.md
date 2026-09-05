---
name: new-route
description: Scaffold a new feature with Route, Service, and Repository following project conventions.
---

Create a new feature following the **Routes > Services > Repositories** architecture.

Follow the [authentication contract](../../docs/contributing.md#authentication-and-sessions)
when adding or changing protected routes.

## What I need from you

1. **Feature name** and a brief description of what it does.
2. Whether it needs **database access** (new model/table, or existing model).
3. Whether it's a **page route** (TemplateResponse), **HTMX route** (HTMLResponse fragment), or **API route** (JSON).
4. Whether it requires **authentication**, and whether it needs only identity or the loaded account.

## What to generate

### Route (`api/routes/`)
- Add to an existing route file or create a new one with `APIRouter(prefix="...", tags=[...])`.
- Use `async def` for all handlers.
- Use `DbSession` or `DbSessionReadOnly` from `core.database` for database access.
- Use `CurrentUser` or `OptionalCurrentUser` from `core.auth` for identity-only consumers (`.user_id`, `.github_username`). Use `CurrentAccount` or `OptionalCurrentAccount` for account/profile consumers (`.id`, loaded fields), including account-aware pages.
- These aliases share one cached account resolver. Treat its loaded account as read-only after the auth transaction closes: no lazy loading, writes, or duplicate account reads for rendering. Pass accounts explicitly to helpers and templates rather than reading `request.state`.
- Page routers use `route_class=LoginRedirectRoute` from `core.routing` for login navigation. API and HTMX routers retain 401 responses.
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
After generating, run: `cd api && uv run ruff check . ../packages/learn-to-cloud-shared && uv run ruff format --check . ../packages/learn-to-cloud-shared && uv run ty check --exclude scripts --exclude tests .`
