# Research: Testing `core/` Module

## Current State

### Test Coverage Map

14 core modules, 6 have dedicated test files, 8 do not:

| Module | Lines | Covered | Test File | Verdict |
|--------|-------|---------|-----------|---------|
| `auth.py` | 36 | **100%** | `tests/core/test_auth.py` | Done |
| `azure_auth.py` | 39 | **97%** | None (tested via `tests/test_database.py`) | Needs dedicated tests |
| `cache.py` | 32 | **91%** | `tests/core/test_cache.py` | Missing user cache tests |
| `config.py` | 74 | **72%** | None | **Needs tests** — validation logic |
| `csrf.py` | 55 | **100%** | `tests/core/test_csrf.py` + `test_csrf_middleware_order.py` | Done |
| `database.py` | 163 | **48%** | `tests/test_database.py` | Covered portions are well tested; uncovered portions are infra wiring |
| `github_client.py` | 19 | **0%** | None | Testable — singleton + lock pattern |
| `llm_client.py` | 21 | **0%** | None | Testable — singleton + config validation |
| `logger.py` | 39 | **85%** | `tests/test_logger.py` | Missing: `_RequestContextFilter` |
| `metrics.py` | 7 | **0%** | None | Low value — OTel no-op instruments |
| `middleware.py` | 43 | **100%** | `tests/core/test_middleware.py` | Done |
| `observability.py` | 85 | **0%** | None | Low value — OTel SDK wiring |
| `ratelimit.py` | 17 | **100%** | `tests/core/test_ratelimit.py` | Done |
| `templates.py` | 4 | **0%** | None | Not worth testing — 1 line of config |

### Modules Already Fully Tested (Skip)

These have **100% coverage** and thorough test files:
- [core/auth.py](api/core/auth.py) → [tests/core/test_auth.py](api/tests/core/test_auth.py)
- [core/csrf.py](api/core/csrf.py) → [tests/core/test_csrf.py](api/tests/core/test_csrf.py)
- [core/middleware.py](api/core/middleware.py) → [tests/core/test_middleware.py](api/tests/core/test_middleware.py)
- [core/ratelimit.py](api/core/ratelimit.py) → [tests/core/test_ratelimit.py](api/tests/core/test_ratelimit.py)

---

## Deep Dive: Each Untested/Under-Tested Module

### 1. `config.py` — Settings Validation (72% → needs tests)

**File**: [api/core/config.py](api/core/config.py) (74 statements, 21 uncovered)

**What it does**: Pydantic `Settings` with env var loading, a `model_validator` for production config checks, and computed properties (`content_dir_path`, `allowed_origins`, `use_azure_postgres`).

**Uncovered lines** (from coverage report): 73, 81-87, 96, 101-104, 109-128, 149

These map to:
- `validate_config` — the `model_validator(mode="after")` that enforces production requirements
- `content_dir_path` — `@cached_property` that resolves content dir from env or default
- `allowed_origins` — `@cached_property` that builds CORS origin list

**Key logic to test**:

| Function/Property | What to test |
|---|---|
| `validate_config` (line 73-87) | DB config required; GitHub creds required in prod; session secret must be changed in prod; all pass in debug mode |
| `use_azure_postgres` (line 96) | True when both `postgres_host` and `postgres_user` set; False otherwise |
| `content_dir_path` (line 101-104) | Custom path from env; default fallback |
| `allowed_origins` (line 109-128) | Debug adds localhost; `frontend_url` added; `cors_allowed_origins` CSV parsed; deduplication |
| `get_settings()` / `clear_settings_cache()` (line 149) | `lru_cache` behavior, cache clearing |

**Dependencies**: Only `pydantic_settings` — no mocking needed. Use `monkeypatch.setenv` to control env vars and construct `Settings` directly.

**Gotcha — `frozen=True`**: Settings instances are immutable. Can't modify after creation — must pass all values to constructor.

**Gotcha — `@lru_cache`**: `get_settings()` is cached. Must call `clear_settings_cache()` in test teardown. The module already provides this function with docstring showing the exact test pattern.

**Gotcha — `@cached_property` on frozen model**: `content_dir_path` and `allowed_origins` use `@cached_property` inside a `frozen=True` Pydantic model. This works because `cached_property` writes to the instance `__dict__` on first access. Tests just need to access the property and assert.

**Proposed approach**:
```python
@pytest.mark.unit
class TestSettingsValidation:
    def test_debug_mode_allows_defaults(self):
        """Debug mode should not require prod-level config."""
        settings = Settings(
            database_url="postgresql+asyncpg://localhost/test",
            debug=True,
        )
        assert settings.debug is True

    def test_prod_requires_github_credentials(self):
        """Production mode should require GitHub OAuth config."""
        with pytest.raises(ValidationError, match="GITHUB_CLIENT_ID"):
            Settings(
                database_url="postgresql+asyncpg://localhost/test",
                debug=False,
            )

    def test_prod_requires_session_secret(self):
        with pytest.raises(ValidationError, match="SESSION_SECRET_KEY"):
            Settings(
                database_url="postgresql+asyncpg://localhost/test",
                debug=False,
                github_client_id="id",
                github_client_secret="secret",
            )

    def test_requires_some_database_config(self):
        """Must set DATABASE_URL or postgres_host+postgres_user."""
        with pytest.raises(ValidationError, match="Database configuration"):
            Settings(debug=True, database_url="", postgres_host="", postgres_user="")
```

---

### 2. `cache.py` — User Cache Gap (91% → minor gap)

**File**: [api/core/cache.py](api/core/cache.py) (32 statements, 3 uncovered)

**Uncovered lines**: 47, 51, 56 — these are:
- `get_cached_user()` (line 47)
- `set_cached_user()` (line 51)
- `invalidate_user_cache()` (line 56)

The existing `test_cache.py` covers progress and phase_detail caches thoroughly but **completely skips user cache functions**.

**Proposed approach**: Add a `TestUserCache` class to the existing [tests/core/test_cache.py](api/tests/core/test_cache.py) file:
```python
@pytest.mark.unit
class TestUserCache:
    def test_set_and_get(self):
        mock_user = MagicMock()
        set_cached_user(1, mock_user)
        assert get_cached_user(1) is mock_user

    def test_get_returns_none_when_not_cached(self):
        assert get_cached_user(999) is None

    def test_invalidate_clears_user(self):
        set_cached_user(1, MagicMock())
        invalidate_user_cache(1)
        assert get_cached_user(1) is None

    def test_invalidate_noop_when_not_cached(self):
        invalidate_user_cache(999)  # Should not raise
```

**Convention**: Add to existing file (not new file) — matches existing pattern where all cache tests live together.

---

### 3. `logger.py` — Missing `_RequestContextFilter` (85% → minor gap)

**File**: [api/core/logger.py](api/core/logger.py) (39 statements, 6 uncovered)

**Uncovered lines**: 40-46 — the `_RequestContextFilter.filter()` method.

This filter reads `request_github_username` context var and injects `github_username` into log records. It's tested *indirectly* via middleware tests, but the filter itself has no direct unit test.

**Proposed approach**: Add to existing [tests/test_logger.py](api/tests/test_logger.py):
```python
@pytest.mark.unit
class TestRequestContextFilter:
    def test_injects_username_from_context_var(self):
        from core.middleware import request_github_username
        token = request_github_username.set("testuser")
        try:
            f = _RequestContextFilter()
            record = logging.LogRecord("test", logging.INFO, "", 0, "msg", (), None)
            f.filter(record)
            assert record.github_username == "testuser"
        finally:
            request_github_username.reset(token)

    def test_does_not_overwrite_explicit_username(self):
        from core.middleware import request_github_username
        token = request_github_username.set("ctx-user")
        try:
            f = _RequestContextFilter()
            record = logging.LogRecord("test", logging.INFO, "", 0, "msg", (), None)
            record.github_username = "explicit-user"
            f.filter(record)
            assert record.github_username == "explicit-user"
        finally:
            request_github_username.reset(token)

    def test_no_username_when_context_var_empty(self):
        f = _RequestContextFilter()
        record = logging.LogRecord("test", logging.INFO, "", 0, "msg", (), None)
        f.filter(record)
        assert not getattr(record, "github_username", None)
```

---

### 4. `github_client.py` — Singleton HTTP Client (0% → testable)

**File**: [api/core/github_client.py](api/core/github_client.py) (19 statements)

**What it does**: Lazy singleton `httpx.AsyncClient` with asyncio.Lock for thread safety. Two functions: `get_github_client()` and `close_github_client()`.

**Key logic to test**:

| Function | What to test |
|---|---|
| `get_github_client()` | Creates client on first call; returns same instance on subsequent calls; creates new client if previous was closed |
| `close_github_client()` | Closes the client; sets global to None; no-op if already None |

**Dependencies**: `get_settings()` for `http_timeout` — mock with `patch`.

**Gotcha — global state**: The module uses `_github_http_client` global. Must reset it between tests:
```python
@pytest.fixture(autouse=True)
async def _reset_github_client():
    import core.github_client as mod
    yield
    if mod._github_http_client is not None and not mod._github_http_client.is_closed:
        await mod._github_http_client.aclose()
    mod._github_http_client = None
```

**Proposed approach**:
```python
@pytest.mark.unit
class TestGetGitHubClient:
    @pytest.mark.asyncio
    async def test_creates_client_on_first_call(self):
        client = await get_github_client()
        assert isinstance(client, httpx.AsyncClient)
        assert not client.is_closed

    @pytest.mark.asyncio
    async def test_returns_same_instance(self):
        c1 = await get_github_client()
        c2 = await get_github_client()
        assert c1 is c2

    @pytest.mark.asyncio
    async def test_recreates_after_close(self):
        c1 = await get_github_client()
        await close_github_client()
        c2 = await get_github_client()
        assert c2 is not c1
        assert not c2.is_closed

@pytest.mark.unit
class TestCloseGitHubClient:
    @pytest.mark.asyncio
    async def test_closes_client(self):
        client = await get_github_client()
        await close_github_client()
        assert client.is_closed

    @pytest.mark.asyncio
    async def test_noop_when_none(self):
        await close_github_client()  # Should not raise
```

---

### 5. `llm_client.py` — Singleton LLM Client (0% → testable)

**File**: [api/core/llm_client.py](api/core/llm_client.py) (21 statements)

**What it does**: Lazy singleton `AzureOpenAIChatClient`. Raises `LLMClientError` if env vars not configured.

**Key logic to test**:

| Function | What to test |
|---|---|
| `get_llm_chat_client()` | Returns cached client; raises `LLMClientError` when not configured; creates client when configured |
| `LLMClientError` | Has `retriable` attribute |

**Dependencies**: `get_settings()` — mock it. `AzureOpenAIChatClient` — mock the import since it requires the agent-framework package.

**Gotcha — global `_llm_client`**: Must reset between tests.

**Proposed approach**:
```python
@pytest.mark.unit
class TestGetLLMChatClient:
    def test_raises_when_not_configured(self):
        mock_settings = MagicMock()
        mock_settings.llm_base_url = ""
        mock_settings.llm_api_key = ""
        with patch("core.llm_client.get_settings", return_value=mock_settings):
            with pytest.raises(LLMClientError, match="not configured"):
                get_llm_chat_client()

    def test_creates_client_when_configured(self):
        mock_settings = MagicMock()
        mock_settings.llm_base_url = "https://example.openai.azure.com"
        mock_settings.llm_api_key = "test-key"
        mock_settings.llm_model = "gpt-5-mini"
        mock_settings.llm_api_version = "2024-10-21"
        with (
            patch("core.llm_client.get_settings", return_value=mock_settings),
            patch("core.llm_client.AzureOpenAIChatClient") as MockClient,
        ):
            # Need to import inside function since AzureOpenAIChatClient is TYPE_CHECKING guarded
            result = get_llm_chat_client()
            MockClient.assert_called_once()

    def test_returns_cached_instance(self):
        # Set _llm_client directly, then verify same object returned
        ...

class TestLLMClientError:
    def test_retriable_attribute(self):
        err = LLMClientError("fail", retriable=True)
        assert err.retriable is True
        err2 = LLMClientError("fail")
        assert err2.retriable is False
```

---

### 6. `config.py` — `allowed_origins` and `content_dir_path`

**What to test beyond `validate_config`**:

```python
@pytest.mark.unit
class TestUseAzurePostgres:
    def test_true_when_both_set(self):
        s = Settings(debug=True, postgres_host="host", postgres_user="user")
        assert s.use_azure_postgres is True

    def test_false_when_host_missing(self):
        s = Settings(debug=True, database_url="postgresql+asyncpg://localhost/db")
        assert s.use_azure_postgres is False

@pytest.mark.unit
class TestAllowedOrigins:
    def test_debug_includes_localhost(self):
        s = Settings(debug=True, database_url="postgresql+asyncpg://localhost/db")
        assert "http://localhost:3000" in s.allowed_origins

    def test_prod_excludes_localhost(self):
        s = Settings(
            database_url="postgresql+asyncpg://localhost/db",
            debug=False,
            github_client_id="id",
            github_client_secret="secret",
            session_secret_key="prod-secret-that-is-secure",
        )
        assert "http://localhost:3000" not in s.allowed_origins

    def test_cors_allowed_origins_parsed(self):
        s = Settings(
            debug=True,
            database_url="postgresql+asyncpg://localhost/db",
            cors_allowed_origins="https://a.com,https://b.com",
        )
        assert "https://a.com" in s.allowed_origins
        assert "https://b.com" in s.allowed_origins

    def test_frontend_url_included(self):
        s = Settings(
            debug=True,
            database_url="postgresql+asyncpg://localhost/db",
            frontend_url="https://app.example.com",
        )
        assert "https://app.example.com" in s.allowed_origins

    def test_deduplication(self):
        s = Settings(
            debug=True,
            database_url="postgresql+asyncpg://localhost/db",
            frontend_url="http://localhost:4280",  # already in debug defaults
        )
        count = s.allowed_origins.count("http://localhost:4280")
        assert count == 1
```

---

### 7. Modules NOT Worth Unit Testing

| Module | Lines | Why Skip |
|---|---|---|
| `metrics.py` | 7 | Declares OTel counter/histogram instruments. If OTel isn't configured, they return no-op stubs. Zero business logic. Testing would just verify `create_counter()` was called. |
| `observability.py` | 85 | Pure SDK wiring — `configure_azure_monitor()`, `_configure_otlp()`, `instrument_app()`. Testing would mock every OTel SDK class and verify `.instrument()` was called. Fragile, zero value. Would break on any OTel SDK update. |
| `templates.py` | 4 | `templates = Jinja2Templates(directory=...)`. One line. Nothing to test. |
| `database.py` uncovered portions | ~85 | `create_engine()`, `create_session_maker()`, `warm_pool()`, `init_db()`, `comprehensive_health_check()` — infrastructure wiring that's exercised by the real app/integration tests. The `test_database.py` file already covers the *logic-bearing* parts (credential locking, retry, pool checkout, get_db semantics). |

---

## Existing Test Patterns (from reading all 6 existing core test files)

The core test files follow the same conventions as service tests, with these additions:

1. **Fixture to save/restore global state** — seen in `test_logger.py`:
   ```python
   @pytest.fixture(autouse=True)
   def _clean_root_logger():
       root = logging.getLogger()
       original_handlers = root.handlers[:]
       original_level = root.level
       yield
       root.handlers = original_handlers
       root.setLevel(original_level)
   ```

2. **ASGI scope helpers** — seen in `test_csrf.py` and `test_middleware.py`:
   ```python
   def _http_scope(method="GET", path="/test", headers=None, session=None) -> dict:
       scope = {"type": "http", "method": method, "path": path, ...}
       if session is not None:
           scope["session"] = session
       return scope
   ```

3. **Directly testing internal classes** — `_JSONFormatter`, `_RequestContextFilter`, `CSRFMiddleware` are all imported and tested directly despite the `_` prefix.

4. **`test_database.py` lives in `tests/` not `tests/core/`** — because it covers both `core/database.py` and `core/azure_auth.py`. New tests should go in `tests/core/` to follow the more standard pattern.

5. **No `@pytest.mark.asyncio` on classes** — only on individual async methods.

6. **`pytest.raises` with `match=`** — error message assertions use substring matching.

---

## Proposed File Plan

| Priority | Action | File |
|---|---|---|
| **1** | Create new | `api/tests/core/test_config.py` — Settings validation, computed properties |
| **2** | Create new | `api/tests/core/test_github_client.py` — singleton lifecycle |
| **3** | Create new | `api/tests/core/test_llm_client.py` — singleton + error handling |
| **4** | Extend existing | `api/tests/core/test_cache.py` — add `TestUserCache` |
| **5** | Extend existing | `api/tests/test_logger.py` — add `TestRequestContextFilter` |

**Do not create tests for**: `metrics.py`, `observability.py`, `templates.py`, remaining `database.py` infra wiring.

---

## Potential Gotchas

### 1. `Settings` Constructor Requires Database Config
Every `Settings()` call needs at least `database_url` or `postgres_host` + `postgres_user`, else the `model_validator` raises. Test helpers must always pass one:
```python
Settings(debug=True, database_url="postgresql+asyncpg://localhost/test")
```

### 2. `get_settings()` `lru_cache`
If any test calls `get_settings()` (even indirectly), it caches the result. Must call `clear_settings_cache()` in teardown or the `github_client` / `llm_client` tests will see stale settings.

### 3. `github_client.py` Global State
`_github_http_client` is module-level. Tests that call `get_github_client()` create a real `httpx.AsyncClient`. Must close it in teardown or it leaks file descriptors.

### 4. `llm_client.py` Import Guard
`AzureOpenAIChatClient` is behind `TYPE_CHECKING`. The real import happens inside `get_llm_chat_client()`. Must either:
- Let the real import happen (requires `agent-framework[azure]` installed — it is in dev deps)
- Or mock the import

### 5. `_RequestContextFilter` Reads Context Vars
Context vars are per-task. In tests, must explicitly `set()` and `reset()` the token, or the value leaks to other tests.

### 6. `Settings` is `frozen=True`
Can't modify Settings after creation. Must construct with all needed values upfront. `@cached_property` still works because it writes to `__dict__` (Pydantic's `frozen` only applies to model fields).

---

## External References

- [pydantic-settings docs](https://docs.pydantic.dev/latest/concepts/pydantic_settings/) — `BaseSettings`, `model_validator`, `frozen`
- [httpx.AsyncClient](https://www.python-httpx.org/async/) — lifecycle, `is_closed`
- [cachetools.TTLCache](https://cachetools.readthedocs.io/en/stable/) — `pop()`, `get()`, `clear()`
- [pytest monkeypatch](https://docs.pytest.org/en/latest/how-to/monkeypatch.html) — `monkeypatch.setenv` for env var tests
- [contextvars](https://docs.python.org/3/library/contextvars.html) — `set()` / `reset()` pattern for test cleanup
