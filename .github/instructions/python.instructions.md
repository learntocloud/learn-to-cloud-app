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

## Caching (cachetools)
- `TTLCache` is **not** thread-safe—always wrap access with `asyncio.Lock`
- Use a separate lock for cache operations
- Example:
  ```python
  _cache: TTLCache[str, Any] = TTLCache(maxsize=100, ttl=300)
  _cache_lock = asyncio.Lock()

  async with _cache_lock:
      _cache[key] = value
  ```

## Logging
- Use **structured logging** via `core.logger`: `logger.info("event.name", key=value)`
- Never interpolate variables into log messages—use keyword args
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

## Comments

### Remove These
- **Obvious/redundant** — restates what code clearly does
- **Commented-out code** — delete it, don't comment it
- **Vague TODOs** — must have context: `TODO(#123): Handle rate limit`
- **Change logs** — version control handles this

### Keep These
- **Why comments** — explain intent/reasoning
- **Non-obvious behavior** — e.g., "PostgreSQL ON CONFLICT doesn't trigger onupdate"
- **Workarounds** — with justification and removal date
- **Warnings** — `# WARNING:` or `# SECURITY:`

### Special Comments
- `# type: ignore` — always add explanation: `# type: ignore[arg-type] - httpx stub incomplete`
- `# noqa` — always include rule: `# noqa: E501`

## Git & Commits

### Pre-Commit (MANDATORY)
```bash
pre-commit run --all-files
```
- **NEVER** use `--no-verify` to bypass
- **NEVER** commit if pre-commit fails—fix all issues first

### Conventional Commits
Format: `type(scope): description`

| Type | Use For |
|------|---------|
| `feat` | New feature |
| `fix` | Bug fix |
| `docs` | Documentation |
| `refactor` | Code restructure |
| `test` | Adding tests |
| `chore` | Deps, config |

Scopes: `api`, `frontend`, `infra`, `content`, `skills`
