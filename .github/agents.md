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

## Conventions an LLM Won't Know

### Database Sessions
- Repositories **never commit** — they only `flush()`. The caller (route/service) owns the transaction via dependency injection.
- Use `DbSession` for writes, `DbSessionReadOnly` for reads. These are `Annotated` type aliases from `core.database`.
- For long-running operations (LLM calls), use a three-phase pattern: read (short session) → validate (no session) → write (fresh session).

### Auth Type Aliases
- `UserId = Annotated[int, Depends(require_auth)]` — use in route signatures for required auth.
- `OptionalUserId = Annotated[int | None, Depends(optional_auth)]` — for pages that work both authenticated and anonymous.
- HTMX requests get 401 responses; browser requests get 307 redirects to OAuth.

### Route Response Types
- **Page routes** (`pages_routes.py`): Return `request.app.state.templates.TemplateResponse()` with `_template_context()` helper.
- **HTMX routes** (`htmx_routes.py`): Return `HTMLResponse` fragments, never full pages. Use `HX-Refresh` header to force full reload.
- **API routes** (`users_routes.py`): Return JSON via `response_model=`. Only these are in the OpenAPI schema (`include_in_schema=True`).

### Logging
- Structured logging with `extra={}` dicts — never f-strings for log messages.
- Event names use dot-notation: `"user.account_deleted"`, `"step.completed"`, `"auth.callback.failed"`.
- Always include relevant IDs in extra: `user_id`, `step_id`, `phase_id`, `requirement_id`.
- Use `logger.exception()` in except blocks (auto-includes traceback).

### Singletons & Config
- HTTP clients (`get_github_client()`, `get_llm_client()`) are module-level singletons with lazy init and asyncio locks. Never create per-request.
- Call `get_settings()` at function level, not module level. Settings are frozen (Pydantic `BaseSettings` with `frozen=True`).

### Service Layer
- Verification services return `ValidationResult(is_valid, message, task_results=[...])`.
- Custom exceptions carry a `retriable: bool` flag to distinguish transient from permanent failures.
- External API calls use circuit breaker + retry decorators (pybreaker + tenacity).
- LLM verifications use shared utilities from `llm_verification_base.py`: `parse_structured_response()`, `build_task_results()`, `sanitize_feedback()`.
- Token verifications (CTF, networking) use shared flow from `token_verification_base.py` with `LabConfig` dataclass.

### Concurrency
- Per-user+requirement locks prevent duplicate concurrent submissions.
- Global `Semaphore(3)` caps concurrent LLM calls to avoid pool exhaustion.
- Submission rate limiting: daily cap + per-requirement cooldown for LLM-based verification.

### Template Hierarchy
- Content pages extend `layouts/content_page.html` (provides breadcrumb + header + body blocks).
- Full-bleed pages (home, curriculum, phase, 404) extend `base.html` directly.
- Partials receive context via `{% with %}` blocks.
- Out-of-band HTMX updates (`hx-swap-oob="true"`) used for progress bars after step completion.

### Tailwind CSS v4
- Config lives in `api/static/css/input.css` — there is no `tailwind.config.js`.
- Dark mode: `@custom-variant dark (&:where(.dark, .dark *))` — class-based, toggled by Alpine.js + localStorage.
- Renamed utilities (v4): `shadow-xs` (was `shadow-sm`), `rounded-xs` (was `rounded-sm`), `outline-hidden` (was `outline-none`), `ring-3` (was `ring`).

### Content YAML Schema
- Phase metadata: `content/phases/phaseN/_phase.yaml`
- Topic files: `content/phases/phaseN/topic-slug.yaml`
- Step IDs: `phase{N}-topic{N}-{action}-{slug}` (lowercase kebab-case, must be unique within topic)
- Action types: Watch, Read, Explore, Practice
- Multi-provider steps use `options` array sorted Azure → AWS → GCP → other

### Terraform / Azure
- Resource naming: `<service-code>-ltc-<purpose>-${var.environment}[-${local.suffix}]`
- Auth: Managed Identity (Entra ID) for database and Azure services — no passwords in infra.
- One `.tf` file per resource type.

### Testing
- `asyncio_mode = auto` — no manual `@pytest.mark.asyncio` needed.
- Always tag tests: `@pytest.mark.unit` or `@pytest.mark.integration`.
- `db_session` fixture auto-rolls back transactions. Tests skip if local PostgreSQL unavailable.
- Mock with `autospec=True` always. Use `AsyncMock()` for async methods.

### Toolchain: uv
- **All Python commands go through `uv run`** — never bare `python`, `pytest`, `ruff`, etc.
  - `uv run pytest` (not `pytest`)
  - `uv run ruff check .` (not `ruff check .`)
  - `uv run python -m uvicorn main:app` (not `python -m uvicorn`)
- Install dependencies: `uv sync` (not `pip install`). Lock file is `uv.lock`.
- Add a dependency: `uv add <package>` (not `pip install` + manual requirements edit).
- Create venv: `uv venv` (not `python -m venv`). Python 3.13+ required.

### Pre-commit
- Run `uv run prek run --all-files` before committing. Tools: ruff lint, ruff format, ty type-check.

### Observability
- `configure_azure_monitor()` must run **before** FastAPI is imported for auto-instrumentation to work.
- Auto-traced: HTTP requests, SQLAlchemy queries, outbound httpx, LLM calls. Don't add manual OTel spans.
