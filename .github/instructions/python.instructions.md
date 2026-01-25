---
applyTo: '**/*.py'
---

# Python Coding Standards

## Style
- Follow PEP 8
- Use type hints for all function signatures
- Use async/await for all database operations
- Maximum line length: 88 characters (ruff default)

## Type Hints (Modern Syntax)
- Use `X | None` not `Optional[X]` (PEP 604)
- Use `list[str]` not `List[str]` (PEP 585)
- Use `dict[str, Any]` not `Dict[str, Any]`
- Use `type[T]` for class types
- For generics: `def func[T](item: T) -> T:` (PEP 695, Python 3.12+)

## Imports
- Group imports: stdlib → third-party → local
- Use absolute imports within the api package
- Sort imports alphabetically within groups

## Naming
- Functions/variables: `snake_case`
- Classes: `PascalCase`
- Constants: `UPPER_SNAKE_CASE`

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
- Use **structlog** via `core.logger`: `from core.logger import get_logger`
- **CRITICAL**: structlog uses **keyword arguments**, NOT stdlib's `extra={}` dict:
  ```python
  # ✅ CORRECT - structlog pattern
  logger.info("user.created", user_id=user.id, email=user.email)
  logger.error("payment.failed", order_id=order.id, reason="declined")

  # ❌ WRONG - stdlib pattern (will NOT add fields to JSON output)
  logger.info("User created", extra={"user_id": user.id})
  ```
- First argument is the **event name** (dot-notation), not a human message
- Never interpolate variables into event names—use keyword args for all context
- Use `logger.exception()` inside except blocks to include stack trace
- Use **wide events** for request-scoped context that should appear in canonical log lines:
  ```python
  from core.wide_event import set_wide_event_fields, set_wide_event_nested

  # Add fields to the request's canonical log line
  set_wide_event_fields(cart_id=cart.id, items_count=len(cart.items))

  # For nested categories
  set_wide_event_nested("user", id=user.id, plan="premium")
  ```
- Wide events are emitted once per request by middleware—use for metrics/observability
- Use `logger.info/warning/error` for discrete events during the request

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
- Let exceptions propagate to FastAPI's exception handlers when appropriate
- For external API calls, catch specific exceptions and wrap with context:
  ```python
  try:
      response = await client.get(url)
      response.raise_for_status()
  except httpx.HTTPStatusError as e:
      logger.warning("external.api.error", url=url, status=e.response.status_code)
      raise HTTPException(502, "Upstream service error")
  ```
- Document which exceptions a function can raise in docstrings

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
