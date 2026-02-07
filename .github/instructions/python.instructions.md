---
applyTo: "**/*.py"
description: "FastAPI routes, async patterns, structlog logging, SQLAlchemy, httpx clients, TTLCache caching"
---

# Python Coding Standards

## Separation of Concerns (CRITICAL)

### Layer Responsibilities
| Layer | Responsibility | What it DOES | What it does NOT do |
|-------|----------------|--------------|---------------------|
| **Routes** (`routes/`) | HTTP handling | Validate input, call services, return responses, raise `HTTPException` | Business logic, direct DB access, logging business events |
| **Services** (`services/`) | Business logic | Orchestrate operations, enforce rules, log domain events, raise domain exceptions | HTTP concerns, direct SQL, commit transactions |
| **Repositories** (`repositories/`) | Data access | Execute queries, return models/DTOs | Business rules, HTTP exceptions, commit transactions |

### Exception Handling Rules
1. **Services** raise **domain exceptions** (e.g., `StepNotFoundError`, `ScenarioGenerationFailed`)
2. **Routes** catch domain exceptions and convert to `HTTPException`:
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
3. **Never** let raw exceptions (KeyError, ValueError) escape to users—wrap with context

### Logging Guidelines
- **Routes**: Log at request boundaries only if adding context beyond middleware
- **Services**: Log **domain events** using dot-notation event names:
  ```python
  logger.info("step.completed", user_id=user_id, step_id=step_id, phase=phase_id)
  logger.warning("badge.computation.skipped", reason="no_progress_data")
  ```
- **Repositories**: Generally no logging (too noisy)—let SQLAlchemy instrumentation handle query tracing

### Telemetry Guidelines
See [observability.instructions.md](observability.instructions.md) for wide events, tracing, and metrics.

## Style & Type Hints
- Follow PEP 8; max line length 88 (ruff enforces)
- Use type hints on all function signatures
- Modern syntax: `X | None` not `Optional[X]`, `list[str]` not `List[str]`, `dict[str, Any]` not `Dict`
- For generics (Python 3.12+): `def func[T](item: T) -> T:`
- Use absolute imports within the api package

## HTTP Clients (httpx)
- **Never** create `httpx.AsyncClient()` per request—use a shared module-level client
- Use `_get_http_client()` pattern with lazy initialization and `asyncio.Lock`
- Always provide a `close_*_client()` function for shutdown cleanup
- Register cleanup in `main.py` lifespan handler
- Example pattern:
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

## Caching (In-Memory TTLCache)
- Use `cachetools.TTLCache` for in-memory caching—**no Redis**
- Cache is **per-worker/replica**, not shared across instances
- Suitable for data tolerating short-term staleness (30-60s)
- For shared caches, use `core.cache` module (`get_cached_progress`, `set_cached_progress`, etc.)
- For service-specific caches, use local `TTLCache` with `asyncio.Lock`:
  ```python
  from cachetools import TTLCache

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
- `TTLCache` is **not** thread-safe—always wrap read AND write with `asyncio.Lock`
- Call `invalidate_*_cache()` after mutations that affect cached data

## Logging (structlog)
- Import: `from core.logger import get_logger` → `logger = get_logger(__name__)` at module level
- **CRITICAL**: structlog uses **keyword arguments**, NOT stdlib's `extra={}` dict:
  ```python
  # ✅ CORRECT
  logger.info("user.created", user_id=user.id, email=user.email)

  # ❌ WRONG - stdlib pattern (fields won't appear in JSON)
  logger.info("User created", extra={"user_id": user.id})

  # ❌ WRONG - f-string (loses structured data)
  logger.info(f"User {user.id} created")
  ```
- First argument is **event name** (dot-notation: `domain.action.result`), not a message
- Use `logger.exception()` in except blocks—auto-includes traceback
- See **Logging Guidelines** in Separation of Concerns for what to log where

## FastAPI Routes
- Always add `@limiter.limit()` decorator for public endpoints
- Include OpenAPI docs: `summary=`, `responses=` in route decorator
- Use Pydantic `response_model` for type safety
- **Route ordering matters**: declare literal paths (`/items/stats`) BEFORE parameterized paths (`/items/{id}`)
- POST endpoints should return status code 201: `@router.post(..., status_code=201)`
- DELETE endpoints should return 204 (no content) or 200 with deleted resource
- Use `Annotated[T, Depends(...)]` pattern for dependency injection
- Document binary responses (PDF, images) with `responses={200: {"content": {...}}}`
- Example:
  ```python
  @router.get(
      "",
      response_model=MyResponse,
      summary="Short description",
      responses={500: {"description": "Service unavailable"}},
  )
  @limiter.limit("30/minute")
  async def my_endpoint(request: Request): ...
  ```

## Dependencies
- Managed with `uv` (not pip)
- Add to `pyproject.toml`, not requirements.txt
- Run `uv sync` to install
- Use the existing `api/.venv` created by `uv` (do not create a separate venv)
- Run tools via `uv run --directory api ...` to ensure the repo venv is used

## Testing
- Test files: `test_*.py`
- Use pytest fixtures from `conftest.py`
- Mock external services (Clerk, LLM, GitHub API)
- **Always** use `autospec=True` when mocking—prevents mock drift
- Use `# pragma: no cover` for `if __name__ == "__main__":` blocks
- Prefer behavior tests over mock assertion tests when possible
- Use `@pytest.mark.parametrize` for data-driven tests
- Use `pytest-asyncio` with `@pytest.mark.asyncio` for async tests
- Debugging: `pytest --lf` (last failed), `--pdb` (debugger at failure)

## Async Patterns
- Use `asyncio.Lock` for protecting shared mutable state
- Use `async with` for context managers (sessions, locks, clients)
- Prefer `asyncio.gather()` for concurrent independent operations
- Never block the event loop with synchronous I/O

## Error Handling
- **Define domain exceptions** in services or a shared `exceptions.py`:
  ```python
  class StepNotFoundError(Exception):
      """Raised when a step ID doesn't exist."""
      def __init__(self, step_id: str):
          self.step_id = step_id
          super().__init__(f"Step not found: {step_id}")

  class StepAlreadyCompleteError(Exception):
      """Raised when attempting to complete an already-completed step."""
      pass
  ```
- **Services** raise domain exceptions, **routes** convert to HTTPException:
  ```python
  # In routes/steps_routes.py
  try:
      result = await step_service.complete_step(db, user_id, step_id)
  except StepNotFoundError as e:
      raise HTTPException(status_code=404, detail=str(e))
  except StepAlreadyCompleteError:
      raise HTTPException(status_code=400, detail="Step already completed")
  ```
- For external API calls, catch specific exceptions and log with context:
  ```python
  try:
      response = await client.get(url)
      response.raise_for_status()
  except httpx.HTTPStatusError as e:
      logger.warning("external.api.error", url=url, status=e.response.status_code)
      raise ExternalServiceError("Upstream service error") from e
  ```
- Use `logger.exception()` for unexpected errors (includes traceback automatically)
- **Never** catch bare `Exception` unless re-raising or logging—be specific
- Document which exceptions a function can raise in docstrings:
  ```python
  async def complete_step(db: AsyncSession, user_id: str, step_id: str) -> StepProgress:
      """Mark a step as complete for a user.

      Raises:
          StepNotFoundError: If step_id doesn't exist in content.
          StepAlreadyCompleteError: If user already completed this step.
      """
  ```

## SQLAlchemy Patterns
- Always use `async_sessionmaker` and `AsyncSession`
- Use `select()` style queries (SQLAlchemy 2.0 syntax)
- For upserts, use `pg_insert().on_conflict_do_update()` with explicit `set_`
- Remember: Python-side column defaults are NOT applied on conflict update—include `updated_at` explicitly
- Use `begin_nested()` for savepoints when catching `IntegrityError`
- Use `flush()` inside transactions, `commit()` at boundaries
- Repository methods should NOT call `commit()`—caller owns the transaction
- Use `scalar_one()` vs `scalar_one_or_none()` correctly based on expected results

## Docstrings
- Required on all public functions
- Skip Args that are self-documenting from type hints (e.g., `db: AsyncSession`)
- Keep Args that add semantic meaning beyond the type
- Skip Returns section if return type annotation is clear
- Keep Warning/Note sections for non-obvious behavior
- Compress verbose explanations

## Special Comments
- `# type: ignore` — always add explanation: `# type: ignore[arg-type] - httpx stub incomplete`
- `# noqa` — always include rule: `# noqa: E501`

---

## Feedback
If you encounter a pattern, convention, or edge case that should be added to these instructions, let me know so we can consider including it.
