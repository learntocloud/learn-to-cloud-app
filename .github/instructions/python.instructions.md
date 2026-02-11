---
applyTo: "**/*.py"
description: "FastAPI routes, async patterns, stdlib logging, SQLAlchemy, httpx clients, TTLCache caching"
---

# Python Coding Standards

## API Contract
Pydantic models in `api/schemas.py` and `api/models.py` are the source of truth.
Reference those files for type information and endpoint contracts when working on routes.

## Architecture Layers (CRITICAL)

| Layer | Does | Does NOT |
|-------|------|----------|
| **Routes** (`routes/`) | Validate input, call services, return responses, raise `HTTPException` | Business logic, direct DB access |
| **Services** (`services/`) | Orchestrate operations, enforce rules, log domain events, raise domain exceptions, commit transactions | HTTP concerns, direct SQL |
| **Repositories** (`repositories/`) | Execute queries, return models/DTOs | Business rules, HTTP exceptions, commit transactions |

## Exception Handling

**Services** raise domain exceptions → **Routes** convert to `HTTPException`:
```python
# ✅ CORRECT - Route catches domain exception
try:
    result = await step_service.complete_step(db, user_id, step_id)
except StepNotFoundError as e:
    raise HTTPException(status_code=404, detail=str(e))
except StepAlreadyCompleteError:
    raise HTTPException(status_code=400, detail="Step already completed")

# ❌ WRONG - Service raises HTTPException
async def complete_step(...):
    if not step:
        raise HTTPException(404, "Not found")  # Don't do this in services!
```

**Define domain exceptions** in services or a shared `exceptions.py`:
```python
class StepNotFoundError(Exception):
    def __init__(self, step_id: str):
        self.step_id = step_id
        super().__init__(f"Step not found: {step_id}")
```

For external API calls, catch specific exceptions and chain with `from`:
```python
try:
    response = await client.get(url)
    response.raise_for_status()
except httpx.HTTPStatusError as e:
    logger.warning("external.api.error", extra={"url": url, "status": e.response.status_code})
    raise ExternalServiceError("Upstream service error") from e
```

- Document raiseable exceptions in docstrings

## Logging (stdlib)

Declare a module-level logger via stdlib—no wrapper function needed:
```python
import logging

logger = logging.getLogger(__name__)
```

**CRITICAL**: Pass structured context via `extra={}` dict—never f-strings:
```python
# ✅ CORRECT - extra dict becomes queryable in App Insights
logger.info("user.created", extra={"user_id": user.id, "email": user.email})

# ❌ WRONG - f-string (loses structured data)
logger.info(f"User {user.id} created")

# ❌ WRONG - keyword args (that's structlog, not stdlib)
logger.info("user.created", user_id=user.id)
```

- First argument is an **event name** (dot-notation: `domain.action`), not a sentence
- Use `logger.exception()` in except blocks—auto-includes traceback
- **Where to log**: Services log domain events. Routes log only if adding context beyond middleware. Repositories generally don't log.

See [observability.instructions.md](observability.instructions.md) for tracing and telemetry.

## HTTP Clients (httpx)
**Never** create `httpx.AsyncClient()` per request—use a shared module-level client with lazy init:
```python
_http_client: httpx.AsyncClient | None = None
_client_lock = asyncio.Lock()

async def _get_http_client() -> httpx.AsyncClient:
    global _http_client
    async with _client_lock:
        if _http_client is None:
            _http_client = httpx.AsyncClient(timeout=30.0)
        return _http_client
```
Always provide a `close_*_client()` function and register it in `main.py` lifespan.

## Caching (TTLCache)
- Use `cachetools.TTLCache`—**no Redis**. Cache is per-worker/replica.
- For shared caches, use `core.cache` module (`get_cached_progress`, etc.)
- For service-specific caches, wrap with `asyncio.Lock` (TTLCache is not thread-safe):
  ```python
  _cache: TTLCache[str, Any] = TTLCache(maxsize=100, ttl=300)
  _cache_lock = asyncio.Lock()

  async with _cache_lock:
      cached = _cache.get(key)
      if cached is not None:
          return cached
  # ... fetch data ...
  async with _cache_lock:
      _cache[key] = value
  ```
- `core.cache` skips locks (single-threaded, no `await` between read/write)—new caches should still use locks
- Call `invalidate_*_cache()` after mutations

## FastAPI Routes
- `@limiter.limit()` on mutating API and HTMX endpoints (pages/auth redirect routes exempt)
- Include `summary=`, `responses=` for OpenAPI JSON API docs
- **Route ordering**: literal paths (`/items/stats`) BEFORE parameterized (`/items/{id}`)
- DELETE → 204 or 200
- Use pre-built DI aliases from `core.auth` and `core.database`:
  ```python
  from core.auth import UserId, OptionalUserId
  from core.database import DbSession, DbSessionReadOnly
  ```
  These wrap `Annotated[T, Depends(...)]`—use them instead of raw `Depends()` calls.
- Example:
  ```python
  @router.get(
      "",
      response_model=MyResponse,
      summary="Short description",
      responses={500: {"description": "Service unavailable"}},
  )
  @limiter.limit("30/minute")
  async def my_endpoint(
      request: Request, user_id: UserId, db: DbSession
  ) -> MyResponse: ...
  ```

## Dependencies
- Managed with `uv` (not pip) — add to `pyproject.toml`, run `uv sync`
- Use the existing `api/.venv` (do not create a separate venv)
- Run tools via `uv run --directory api ...`

## Testing
- Mock external services (LLM, GitHub API) with `autospec=True`

## SQLAlchemy Patterns
- Upserts: `pg_insert().on_conflict_do_update()` with explicit `set_`
- **Gotcha**: Python-side column defaults are NOT applied on conflict update—include `updated_at` explicitly
- Repository methods do NOT call `commit()`—services own the transaction and call `await db.commit()`

## Docstrings
- Skip self-documenting Args (e.g., `db: AsyncSession`)
- Keep Warning/Note sections for non-obvious behavior
