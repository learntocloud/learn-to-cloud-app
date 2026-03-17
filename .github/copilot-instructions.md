# Project Instructions

## Architecture

FastAPI backend serving server-rendered HTML (Jinja2 + HTMX + Alpine.js). No SPA — the server is the source of truth.

```
api/
  core/           # Config, auth, database, middleware, logging, observability
  routes/         # Page routes (TemplateResponse), HTMX routes (HTML fragments), API routes (JSON)
  services/       # Business logic, LLM verification, token verification
  repositories/   # Data access (async SQLAlchemy, never commit — only flush)
  rendering/      # Template context builders (keep routes thin)
  templates/      # Jinja2: base.html → layouts/ → pages/, partials/ for fragments
  models.py       # SQLAlchemy models (source of truth for DB schema)
  schemas.py      # Pydantic models (source of truth for API contract)
content/          # Course content as YAML (phases/phaseN/*.yaml)
infra/            # Terraform for Azure (Container Apps, PostgreSQL, OpenAI)
```

## Tech Stack

- **Backend**: FastAPI 0.115 + Python 3.13, async throughout
- **Database**: PostgreSQL 16 via async SQLAlchemy 2.0 + asyncpg, Alembic migrations
- **Frontend**: Jinja2 templates + HTMX + Tailwind CSS v4 + Alpine.js
- **Auth**: GitHub OAuth via Authlib, Azure Managed Identity in prod
- **Observability**: Azure Monitor OpenTelemetry
- **Infra**: Azure Container Apps, Terraform

## Code Style

- Ruff for linting + formatting (line-length 88, target py313)
- ty for type checking
- Strict typing with `Mapped[]` and `mapped_column()` — no `Any` unless unavoidable
- Async/await everywhere — no sync database calls

## Conventions an LLM Won't Know

### Database Sessions
- Repositories **never commit** — they only `flush()`. The caller (route/service) owns the transaction via dependency injection.
- Use `DbSession` for writes, `DbSessionReadOnly` for reads. These are `Annotated` type aliases from `core.database`.

### Auth Type Aliases
- `UserId = Annotated[int, Depends(require_auth)]` — use in route signatures for required auth.
- `OptionalUserId = Annotated[int | None, Depends(optional_auth)]` — for pages that work both authenticated and anonymous.

### Route Response Types
- **Page routes** (`pages_routes.py`): Return `request.app.state.templates.TemplateResponse()` with `_template_context()` helper.
- **HTMX routes** (`htmx_routes.py`): Return `HTMLResponse` fragments, never full pages.
- **API routes** (`users_routes.py`): Return JSON via `response_model=`. Only these are in the OpenAPI schema.

### Logging
- Structured logging with `extra={}` dicts — never f-strings for log messages.
- Event names use dot-notation: `"user.account_deleted"`, `"step.completed"`.
- Always include relevant IDs in extra: `user_id`, `step_id`, `phase_id`.
- Use `logger.exception()` in except blocks (auto-includes traceback).

### Singletons & Config
- HTTP clients (`get_github_client()`, `get_llm_client()`) are module-level singletons with lazy init and asyncio locks. Never create per-request.
- Call `get_settings()` at function level, not module level. Settings are frozen.

### Service Layer
- Verification services return `ValidationResult(is_valid, message, task_results=[...])`.
- Custom exceptions carry a `retriable: bool` flag.
- External API calls use circuit breaker + retry decorators (pybreaker + tenacity).

### Template Hierarchy
- Content pages extend `layouts/content_page.html`.
- Partials receive context via `{% with %}` blocks.
- Out-of-band HTMX updates (`hx-swap-oob="true"`) used for progress bars after step completion.

### Tailwind CSS v4
- Config lives in `api/static/css/input.css` — there is no `tailwind.config.js`.
- Dark mode: class-based, toggled by Alpine.js + localStorage.
- Renamed utilities (v4): `shadow-xs` (was `shadow-sm`), `rounded-xs` (was `rounded-sm`), `outline-hidden` (was `outline-none`).

### Terraform / Azure
- Resource naming: `<service-code>-ltc-<purpose>-${var.environment}[-${local.suffix}]`
- Auth: Managed Identity (Entra ID) — no passwords in infra.
- One `.tf` file per resource type.

### Testing
- `asyncio_mode = auto` — no manual `@pytest.mark.asyncio` needed.
- Always tag tests: `@pytest.mark.unit` or `@pytest.mark.integration`.
- `db_session` fixture auto-rolls back transactions.
- Mock with `autospec=True` always. Use `AsyncMock()` for async methods.

### Toolchain: uv
- **All Python commands go through `uv run`** — never bare `python`, `pytest`, `ruff`, etc.
- Install dependencies: `uv sync`. Add a dependency: `uv add <package>`.

### Pre-commit
- Run `uv run prek run --all-files` before committing. Tools: ruff lint, ruff format, ty type-check.
