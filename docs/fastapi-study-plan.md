# FastAPI Tutorial → Learn to Cloud Codebase Study Plan

Study the [FastAPI Tutorial](https://fastapi.tiangolo.com/tutorial/) using this codebase as your real-world reference. Each section links to the official docs and points to the files that implement that concept.

---

## 1. First Steps

**Tutorial:** https://fastapi.tiangolo.com/tutorial/first-steps/

| Concept | File | What to look at |
|---|---|---|
| Creating the `FastAPI()` instance | [main.py L261-268](../api/main.py) | `app = fastapi.FastAPI(title=..., version=..., lifespan=...)` |
| First route / path operation | [health_routes.py L17-19](../api/routes/health_routes.py) | `@router.get("/health")` returning a simple `HealthResponse` |

---

## 2. Path Parameters

**Tutorial:** https://fastapi.tiangolo.com/tutorial/path-params/

| Concept | File | What to look at |
|---|---|---|
| Path params with type hints | [pages_routes.py L100-105](../api/routes/pages_routes.py) | `@router.get("/phase/{phase_id:int}")` |
| Multiple path params | [pages_routes.py L150-156](../api/routes/pages_routes.py) | `"/phase/{phase_id:int}/{topic_slug}"` |
| Path params in HTMX routes | [htmx_routes.py L141-145](../api/routes/htmx_routes.py) | `@router.delete("/steps/{topic_id}/{step_id}")` |
| SSE stream with path param | [htmx_routes.py L423-428](../api/routes/htmx_routes.py) | `"/verification/{requirement_id}/stream"` |

---

## 3. Query Parameters

**Tutorial:** https://fastapi.tiangolo.com/tutorial/query-params/

This app mostly uses path params and form data rather than query params, but the `Request` object is used directly in several places to access query data. Good exercise: try adding a query param (e.g. `?sort=asc`) to one of the existing routes.

---

## 4. Request Body / Form Data

**Tutorial:** https://fastapi.tiangolo.com/tutorial/body/

| Concept | File | What to look at |
|---|---|---|
| `Form(...)` parameters | [htmx_routes.py L119-123](../api/routes/htmx_routes.py) | `topic_id: str = Form(...), step_id: str = Form(...)` |
| Form with validation constraints | [htmx_routes.py L170-174](../api/routes/htmx_routes.py) | `requirement_id: str = Form(..., max_length=100)` |

---

## 5. Pydantic Models / Schemas

**Tutorial:** https://fastapi.tiangolo.com/tutorial/body/ and https://fastapi.tiangolo.com/tutorial/response-model/

| Concept | File | What to look at |
|---|---|---|
| Base model + inheritance | [schemas.py L24-42](../api/schemas.py) | `UserBase` → `UserResponse` |
| `ConfigDict(frozen=True, from_attributes=True)` | [schemas.py L37](../api/schemas.py) | ORM mode for SQLAlchemy compat |
| `Field(default_factory=list)` | [schemas.py L120](../api/schemas.py) | `options: list[ProviderOption] = Field(default_factory=list)` |
| `@computed_field` with `@property` | [schemas.py L289-298](../api/schemas.py) | `is_complete`, `overall_percentage` on `PhaseProgress` |
| `@field_validator` | [schemas.py L492-500](../api/schemas.py) | `validate_provider` on `ProviderDistribution` |
| Immutable base class pattern | [schemas.py L18-21](../api/schemas.py) | `FrozenModel(BaseModel)` with `frozen=True` |
| Nested models | [schemas.py L159-175](../api/schemas.py) | `Phase` containing `list[Topic]`, `PhaseCapstoneOverview`, etc. |

---

## 6. Response Model

**Tutorial:** https://fastapi.tiangolo.com/tutorial/response-model/

| Concept | File | What to look at |
|---|---|---|
| `response_model=` on route | [health_routes.py L17](../api/routes/health_routes.py) | `response_model=HealthResponse` |
| `response_model=` with auth | [users_routes.py L23-28](../api/routes/users_routes.py) | `response_model=UserResponse` |
| `response_class=HTMLResponse` | [pages_routes.py L65](../api/routes/pages_routes.py) | For server-rendered pages |
| Custom `responses=` docs | [health_routes.py L25-34](../api/routes/health_routes.py) | 503 response schema |

---

## 7. Enum / Predefined Values

**Tutorial:** https://fastapi.tiangolo.com/tutorial/path-params/#predefined-values

| Concept | File | What to look at |
|---|---|---|
| `str, Enum` pattern | [models.py L82-113](../api/models.py) | `SubmissionType(str, PyEnum)` with values like `GITHUB_PROFILE`, `CODE_ANALYSIS` |

---

## 8. Dependencies (Dependency Injection)

**Tutorial:** https://fastapi.tiangolo.com/tutorial/dependencies/

This is one of the **most important** sections — this codebase uses DI heavily.

| Concept | File | What to look at |
|---|---|---|
| `Depends()` for auth | [core/auth.py L93-94](../api/core/auth.py) | `UserId = Annotated[int, Depends(require_auth)]` |
| Optional auth dependency | [core/auth.py L95](../api/core/auth.py) | `OptionalUserId = Annotated[int \| None, Depends(optional_auth)]` |
| DB session dependency | [core/database.py L207-208](../api/core/database.py) | `DbSession = Annotated[AsyncSession, Depends(get_db)]` |
| Read-only DB session | [core/database.py L209](../api/core/database.py) | `DbSessionReadOnly = Annotated[AsyncSession, Depends(get_db_readonly)]` |
| Using `Annotated` for DI | All route functions | `user_id: UserId, db: DbSession` — clean, reusable type aliases |
| Dependency yielding (context mgr) | [core/database.py L188-201](../api/core/database.py) | `get_db()` yields session, commits/rolls back |
| Using deps in routes | [users_routes.py L34-36](../api/routes/users_routes.py) | `async def get_current_user(request, user_id: UserId, db: DbSession)` |

---

## 9. Error Handling / HTTPException

**Tutorial:** https://fastapi.tiangolo.com/tutorial/handling-errors/

| Concept | File | What to look at |
|---|---|---|
| `raise HTTPException(401)` | [core/auth.py L72-78](../api/core/auth.py) | Conditional 401 vs 307 redirect |
| `raise HTTPException(503)` | [health_routes.py L47-50](../api/routes/health_routes.py) | Readiness failures |
| Custom exception handlers | [main.py L275-278](../api/main.py) | `app.add_exception_handler(404, not_found_handler)` |
| `RequestValidationError` handler | [main.py L121-139](../api/main.py) | Custom 422 response format |
| Global 500 handler | [main.py L106-118](../api/main.py) | `global_exception_handler` |
| Rate limit exceeded handler | [core/ratelimit.py L33-44](../api/core/ratelimit.py) | Custom 429 with `Retry-After` header |

---

## 10. APIRouter (Bigger Applications)

**Tutorial:** https://fastapi.tiangolo.com/tutorial/bigger-applications/

| Concept | File | What to look at |
|---|---|---|
| Router with `prefix` + `tags` | [users_routes.py L20](../api/routes/users_routes.py) | `APIRouter(prefix="/api/user", tags=["users"])` |
| Router without schema | [htmx_routes.py L64](../api/routes/htmx_routes.py) | `include_in_schema=False` |
| Centralized router imports | [routes/\_\_init\_\_.py](../api/routes/__init__.py) | All routers re-exported |
| Including routers in app | [main.py L341-347](../api/main.py) | `app.include_router(health_router)` etc. |
| Router ordering matters | [main.py L347](../api/main.py) | Comment: "Must be last to avoid catching API routes" |

---

## 11. Middleware

**Tutorial:** https://fastapi.tiangolo.com/tutorial/middleware/

| Concept | File | What to look at |
|---|---|---|
| `GZipMiddleware` | [main.py L295](../api/main.py) | Built-in compression |
| `CORSMiddleware` | [main.py L298-306](../api/main.py) | Debug-only CORS |
| `SessionMiddleware` | [main.py L285-292](../api/main.py) | Cookie-based sessions |
| Custom ASGI middleware (raw) | [core/middleware.py L19-60](../api/core/middleware.py) | `SecurityHeadersMiddleware` |
| Middleware with context vars | [core/middleware.py L63-100](../api/core/middleware.py) | `UserTrackingMiddleware` with OTel spans |
| CSRF middleware | [core/csrf.py](../api/core/csrf.py) | Synchronizer Token Pattern |
| Middleware ordering validation | [main.py L308-319](../api/main.py) | Runtime check that Session runs before CSRF |

---

## 12. Lifespan Events (Startup/Shutdown)

**Tutorial:** https://fastapi.tiangolo.com/advanced/events/

| Concept | File | What to look at |
|---|---|---|
| `@asynccontextmanager` lifespan | [main.py L198-258](../api/main.py) | `async def lifespan(app)` |
| Startup: create engine, run migrations | [main.py L201-231](../api/main.py) | DB init + Alembic |
| Background tasks at startup | [main.py L233-241](../api/main.py) | Warmup + analytics refresh loop |
| Shutdown: dispose resources | [main.py L244-258](../api/main.py) | Cancel tasks, close clients, dispose engine |

---

## 13. Static Files

**Tutorial:** https://fastapi.tiangolo.com/tutorial/static-files/

| Concept | File | What to look at |
|---|---|---|
| `StaticFiles` mount | [main.py L325-326](../api/main.py) | `app.mount("/static", StaticFiles(...))` |
| Cache-busting with content hashes | [main.py L66-80](../api/main.py) | `_build_static_file_hashes()` |
| `FileResponse` for specific files | [main.py L332-337](../api/main.py) | Favicon with `Cache-Control` headers |

---

## 14. Templates (Jinja2)

**Tutorial:** https://fastapi.tiangolo.com/advanced/templates/

| Concept | File | What to look at |
|---|---|---|
| `Jinja2Templates` setup | [core/templates.py](../api/core/templates.py) | Module-level singleton |
| `templates.TemplateResponse(...)` | [pages_routes.py L70-73](../api/routes/pages_routes.py) | Every page route |
| Adding Jinja2 globals | [main.py L328](../api/main.py) | `templates.env.globals["static_url"] = _static_url` |
| Template partials for HTMX | [htmx_routes.py L103-111](../api/routes/htmx_routes.py) | `templates.get_template("partials/...").render(...)` |

---

## 15. Configuration (pydantic-settings)

**Tutorial:** https://fastapi.tiangolo.com/advanced/settings/

| Concept | File | What to look at |
|---|---|---|
| `BaseSettings` with env file | [core/config.py L10-18](../api/core/config.py) | `SettingsConfigDict(env_file=".env")` |
| `@model_validator` for cross-field checks | [core/config.py L73-94](../api/core/config.py) | Require auth config in prod |
| `@cached_property` | [core/config.py L101-105](../api/core/config.py) | `content_dir_path` |
| `@lru_cache` singleton | [core/config.py L135-137](../api/core/config.py) | `get_settings()` |
| `clear_settings_cache()` for tests | [core/config.py L140-150](../api/core/config.py) | Reset between test cases |

---

## 16. SQL Database (SQLAlchemy)

**Tutorial:** https://fastapi.tiangolo.com/tutorial/sql-databases/

| Concept | File | What to look at |
|---|---|---|
| `DeclarativeBase` | [core/database.py L33-34](../api/core/database.py) | `class Base(DeclarativeBase)` |
| `Mapped[]` + `mapped_column` (modern style) | [models.py L48-75](../api/models.py) | `User` model |
| Relationships | [models.py L65-75](../api/models.py) | `submissions`, `step_progress`, `phase_progress` |
| Async engine + session | [core/database.py L130-174](../api/core/database.py) | `create_async_engine`, `async_sessionmaker` |
| Mixins (`TimestampMixin`) | [models.py L30-44](../api/models.py) | `created_at` / `updated_at` with `@declared_attr` |
| Indexes + constraints | [models.py L117-165](../api/models.py) | Composite indexes, unique constraints |
| Alembic migrations | [alembic.ini](../api/alembic.ini) + [alembic/env.py](../api/alembic/env.py) | Migration config |

---

## 17. Security / Authentication

**Tutorial:** https://fastapi.tiangolo.com/tutorial/security/

| Concept | File | What to look at |
|---|---|---|
| OAuth2 flow (GitHub) | [auth_routes.py](../api/routes/auth_routes.py) | Full login → callback → session flow |
| Session-based auth | [core/auth.py](../api/core/auth.py) | `get_user_id_from_session()` |
| Auth dependency (required) | [core/auth.py L60-81](../api/core/auth.py) | `require_auth()` raises 401 |
| Auth dependency (optional) | [core/auth.py L84-88](../api/core/auth.py) | `optional_auth()` returns `None` |
| CSRF protection | [core/csrf.py](../api/core/csrf.py) | Synchronizer Token pattern via middleware |

---

## 18. Testing

**Tutorial:** https://fastapi.tiangolo.com/tutorial/testing/

| Concept | File | What to look at |
|---|---|---|
| Test directory | [tests/](../api/tests/) | Test files |
| pytest config | [pytest.ini](../api/pytest.ini) | Test runner config |
| Dev dependencies | [pyproject.toml L48-56](../api/pyproject.toml) | `httpx`, `pytest-asyncio`, `factory-boy`, etc. |

---

## 19. Background Tasks / Async

**Tutorial:** https://fastapi.tiangolo.com/tutorial/background-tasks/

| Concept | File | What to look at |
|---|---|---|
| `asyncio.create_task()` for bg work | [htmx_routes.py L289-295](../api/routes/htmx_routes.py) | Fire-and-forget LLM verification |
| SSE streaming for async results | [htmx_routes.py L423-530](../api/routes/htmx_routes.py) | `StreamingResponse` with `text/event-stream` |
| Background warmup at startup | [main.py L141-157](../api/main.py) | `_background_warmup()` |
| Periodic background task | [main.py L239-241](../api/main.py) | `analytics_refresh_loop` |

---

## 20. OpenAPI / Docs

**Tutorial:** https://fastapi.tiangolo.com/tutorial/metadata/

| Concept | File | What to look at |
|---|---|---|
| `title`, `version` metadata | [main.py L262-263](../api/main.py) | App metadata |
| Conditional docs (debug-only) | [main.py L265-268](../api/main.py) | `docs_url=None` in prod |
| `summary=` on routes | [users_routes.py L27](../api/routes/users_routes.py) | `summary="Get current user"` |
| `responses=` for error docs | [users_routes.py L28](../api/routes/users_routes.py) | `401`, `404` response docs |
| `include_in_schema=False` | [auth_routes.py L29-31](../api/routes/auth_routes.py) | Hide internal routes |

---

## 21. Logging

| Concept | File | What to look at |
|---|---|---|
| Structured JSON logging | [core/logger.py](../api/core/logger.py) | `_JSONFormatter` for prod |
| Context var injection | [core/logger.py L32-47](../api/core/logger.py) | `_RequestContextFilter` adds `github_username` |
| Structured event names | Everywhere | Pattern: `"module.action"` e.g. `"auth.login.success"` |

---

## Quick Reference: Which file for which concept

| Want to learn... | Start here |
|---|---|
| How a FastAPI app is assembled | [main.py](../api/main.py) |
| Routing & path operations | [routes/](../api/routes/) — pick any route file |
| Pydantic models & validation | [schemas.py](../api/schemas.py) |
| Dependency injection | [core/auth.py](../api/core/auth.py) + [core/database.py](../api/core/database.py) |
| Database + SQLAlchemy | [models.py](../api/models.py) + [core/database.py](../api/core/database.py) |
| Middleware (ASGI) | [core/middleware.py](../api/core/middleware.py) + [core/csrf.py](../api/core/csrf.py) |
| Configuration | [core/config.py](../api/core/config.py) |
| Error handling | [main.py L90-139](../api/main.py) |
| OAuth / Security | [core/auth.py](../api/core/auth.py) + [routes/auth_routes.py](../api/routes/auth_routes.py) |
| Background tasks + SSE | [routes/htmx_routes.py](../api/routes/htmx_routes.py) |
| Templates (Jinja2) | [core/templates.py](../api/core/templates.py) + [routes/pages_routes.py](../api/routes/pages_routes.py) |

---

## Suggested Study Order

1. **First Steps** → **Path Parameters** → **Response Model** — get comfortable with basic routing
2. **Pydantic Models** — understand `schemas.py` deeply, it's used everywhere
3. **Dependencies** — this is the core pattern; study `UserId`, `DbSession`, `OptionalUserId`
4. **Error Handling** — see how the app layers custom handlers
5. **APIRouter** — understand how `routes/__init__.py` organizes everything
6. **SQL Database** — `models.py` + `core/database.py` together
7. **Security** — trace the full OAuth flow from login to session to auth dependency
8. **Middleware** — read `core/middleware.py` and `core/csrf.py` for raw ASGI patterns
9. **Configuration** — `core/config.py` is a textbook `pydantic-settings` example
10. **Lifespan** — understand startup/shutdown in `main.py`
11. **Background Tasks + SSE** — the most advanced pattern, in `htmx_routes.py`
