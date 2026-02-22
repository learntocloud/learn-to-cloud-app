# Plan: Core Module Tests

## Approach

Fill the test coverage gaps in `core/` by creating 3 new test files and extending 2 existing ones. Focus on modules with **testable business logic** — skip pure infrastructure wiring (`metrics.py`, `observability.py`, `templates.py`).

**Why this approach**: The core layer sits below services and is imported everywhere. Config validation bugs silently break the app at startup. Client singletons have subtle global-state issues. These are cheap to test and high-value to catch.

**Total new tests**: ~34 across 5 files.

---

## Files

| Action | File | Target Module |
|--------|------|---------------|
| Create | `api/tests/core/test_config.py` | `core/config.py` (72% → ~95%) |
| Create | `api/tests/core/test_github_client.py` | `core/github_client.py` (0% → ~100%) |
| Create | `api/tests/core/test_llm_client.py` | `core/llm_client.py` (0% → ~90%) |
| Extend | `api/tests/core/test_cache.py` | `core/cache.py` (91% → 100%) |
| Extend | `api/tests/test_logger.py` | `core/logger.py` (85% → 100%) |

**No files deleted.**

---

## File 1: `api/tests/core/test_config.py`

Tests `Settings` validation, computed properties, and cache helpers.

```python
"""Unit tests for core.config module.

Tests cover:
- Settings model_validator production checks
- use_azure_postgres property
- content_dir_path computed property
- allowed_origins computed property with deduplication
- get_settings / clear_settings_cache lru_cache behavior
"""

import pytest
from pydantic import ValidationError

from core.config import Settings, clear_settings_cache, get_settings


@pytest.fixture(autouse=True)
def _clear_settings():
    """Clear lru_cache between tests."""
    clear_settings_cache()
    yield
    clear_settings_cache()


# ---------------------------------------------------------------------------
# Settings validation
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestSettingsValidation:
    def test_debug_mode_allows_defaults(self):
        settings = Settings(
            database_url="postgresql+asyncpg://localhost/test",
            debug=True,
        )
        assert settings.debug is True

    def test_requires_database_config(self):
        with pytest.raises(ValidationError, match="Database configuration"):
            Settings(debug=True, database_url="", postgres_host="", postgres_user="")

    def test_azure_postgres_satisfies_database_requirement(self):
        settings = Settings(
            debug=True,
            database_url="",
            postgres_host="myhost.postgres.database.azure.com",
            postgres_user="myuser",
        )
        assert settings.use_azure_postgres is True

    def test_prod_requires_github_credentials(self):
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

    def test_prod_accepts_valid_config(self):
        settings = Settings(
            database_url="postgresql+asyncpg://localhost/test",
            debug=False,
            github_client_id="id",
            github_client_secret="secret",
            session_secret_key="a-real-secret-not-the-default",
        )
        assert settings.debug is False


# ---------------------------------------------------------------------------
# use_azure_postgres
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestUseAzurePostgres:
    def test_true_when_both_set(self):
        s = Settings(
            debug=True,
            postgres_host="host.postgres.database.azure.com",
            postgres_user="user",
        )
        assert s.use_azure_postgres is True

    def test_false_when_host_missing(self):
        s = Settings(
            debug=True,
            database_url="postgresql+asyncpg://localhost/db",
        )
        assert s.use_azure_postgres is False

    def test_false_when_user_missing(self):
        s = Settings(
            debug=True,
            database_url="postgresql+asyncpg://localhost/db",
            postgres_host="host",
        )
        assert s.use_azure_postgres is False


# ---------------------------------------------------------------------------
# content_dir_path
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestContentDirPath:
    def test_custom_path_from_setting(self):
        s = Settings(
            debug=True,
            database_url="postgresql+asyncpg://localhost/db",
            content_dir="/custom/path",
        )
        assert s.content_dir_path.as_posix() == "/custom/path"

    def test_default_fallback(self):
        s = Settings(
            debug=True,
            database_url="postgresql+asyncpg://localhost/db",
        )
        assert s.content_dir_path.name == "phases"
        assert "content" in s.content_dir_path.parts


# ---------------------------------------------------------------------------
# allowed_origins
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestAllowedOrigins:
    def test_debug_includes_localhost(self):
        s = Settings(
            debug=True,
            database_url="postgresql+asyncpg://localhost/db",
        )
        assert "http://localhost:3000" in s.allowed_origins
        assert "http://localhost:4280" in s.allowed_origins

    def test_prod_excludes_localhost(self):
        s = Settings(
            database_url="postgresql+asyncpg://localhost/db",
            debug=False,
            github_client_id="id",
            github_client_secret="secret",
            session_secret_key="prod-secret",
        )
        assert "http://localhost:3000" not in s.allowed_origins

    def test_frontend_url_included(self):
        s = Settings(
            debug=True,
            database_url="postgresql+asyncpg://localhost/db",
            frontend_url="https://app.example.com",
        )
        assert "https://app.example.com" in s.allowed_origins

    def test_cors_allowed_origins_csv_parsed(self):
        s = Settings(
            debug=True,
            database_url="postgresql+asyncpg://localhost/db",
            cors_allowed_origins="https://a.com, https://b.com",
        )
        assert "https://a.com" in s.allowed_origins
        assert "https://b.com" in s.allowed_origins

    def test_deduplication(self):
        s = Settings(
            debug=True,
            database_url="postgresql+asyncpg://localhost/db",
            frontend_url="http://localhost:4280",
        )
        count = s.allowed_origins.count("http://localhost:4280")
        assert count == 1


# ---------------------------------------------------------------------------
# get_settings / clear_settings_cache
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestGetSettings:
    def test_returns_same_instance(self, monkeypatch):
        monkeypatch.setenv("DATABASE_URL", "postgresql+asyncpg://localhost/test")
        monkeypatch.setenv("DEBUG", "true")
        s1 = get_settings()
        s2 = get_settings()
        assert s1 is s2

    def test_clear_cache_resets(self, monkeypatch):
        monkeypatch.setenv("DATABASE_URL", "postgresql+asyncpg://localhost/test")
        monkeypatch.setenv("DEBUG", "true")
        s1 = get_settings()
        clear_settings_cache()
        s2 = get_settings()
        assert s1 is not s2
```

---

## File 2: `api/tests/core/test_github_client.py`

Tests the singleton httpx.AsyncClient lifecycle with asyncio.Lock.

```python
"""Unit tests for core.github_client module.

Tests cover:
- get_github_client creates client on first call
- get_github_client returns same instance on subsequent calls
- get_github_client recreates client after close
- close_github_client closes and clears the singleton
- close_github_client is no-op when already None
"""

from unittest.mock import MagicMock, patch

import httpx
import pytest

from core.github_client import close_github_client, get_github_client


@pytest.fixture(autouse=True)
async def _reset_github_client():
    """Reset the module-level singleton between tests."""
    import core.github_client as mod

    yield
    if mod._github_http_client is not None and not mod._github_http_client.is_closed:
        await mod._github_http_client.aclose()
    mod._github_http_client = None


@pytest.mark.unit
class TestGetGitHubClient:
    @pytest.mark.asyncio
    async def test_creates_client_on_first_call(self):
        mock_settings = MagicMock()
        mock_settings.http_timeout = 10.0
        with patch(
            "core.github_client.get_settings",
            autospec=True,
            return_value=mock_settings,
        ):
            client = await get_github_client()
        assert isinstance(client, httpx.AsyncClient)
        assert not client.is_closed

    @pytest.mark.asyncio
    async def test_returns_same_instance(self):
        mock_settings = MagicMock()
        mock_settings.http_timeout = 10.0
        with patch(
            "core.github_client.get_settings",
            autospec=True,
            return_value=mock_settings,
        ):
            c1 = await get_github_client()
            c2 = await get_github_client()
        assert c1 is c2

    @pytest.mark.asyncio
    async def test_recreates_after_close(self):
        mock_settings = MagicMock()
        mock_settings.http_timeout = 10.0
        with patch(
            "core.github_client.get_settings",
            autospec=True,
            return_value=mock_settings,
        ):
            c1 = await get_github_client()
            await close_github_client()
            c2 = await get_github_client()
        assert c2 is not c1
        assert not c2.is_closed


@pytest.mark.unit
class TestCloseGitHubClient:
    @pytest.mark.asyncio
    async def test_closes_client(self):
        mock_settings = MagicMock()
        mock_settings.http_timeout = 10.0
        with patch(
            "core.github_client.get_settings",
            autospec=True,
            return_value=mock_settings,
        ):
            client = await get_github_client()
        await close_github_client()
        assert client.is_closed

    @pytest.mark.asyncio
    async def test_noop_when_none(self):
        await close_github_client()  # Should not raise

    @pytest.mark.asyncio
    async def test_sets_global_to_none(self):
        import core.github_client as mod

        mock_settings = MagicMock()
        mock_settings.http_timeout = 10.0
        with patch(
            "core.github_client.get_settings",
            autospec=True,
            return_value=mock_settings,
        ):
            await get_github_client()
        await close_github_client()
        assert mod._github_http_client is None
```

---

## File 3: `api/tests/core/test_llm_client.py`

Tests the LLM client singleton and error handling.

```python
"""Unit tests for core.llm_client module.

Tests cover:
- LLMClientError has retriable attribute
- get_llm_chat_client raises when not configured
- get_llm_chat_client creates client when configured
- get_llm_chat_client returns cached instance
"""

from unittest.mock import MagicMock, patch

import pytest

from core.llm_client import LLMClientError, get_llm_chat_client


@pytest.fixture(autouse=True)
def _reset_llm_client():
    """Reset the module-level singleton between tests."""
    import core.llm_client as mod

    mod._llm_client = None
    yield
    mod._llm_client = None


# ---------------------------------------------------------------------------
# LLMClientError
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestLLMClientError:
    def test_retriable_defaults_to_false(self):
        err = LLMClientError("fail")
        assert err.retriable is False

    def test_retriable_can_be_set(self):
        err = LLMClientError("fail", retriable=True)
        assert err.retriable is True

    def test_message_preserved(self):
        err = LLMClientError("something broke")
        assert str(err) == "something broke"


# ---------------------------------------------------------------------------
# get_llm_chat_client
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestGetLLMChatClient:
    def test_raises_when_base_url_missing(self):
        mock_settings = MagicMock()
        mock_settings.llm_base_url = ""
        mock_settings.llm_api_key = "key"
        with (
            patch(
                "core.llm_client.get_settings",
                autospec=True,
                return_value=mock_settings,
            ),
            pytest.raises(LLMClientError, match="not configured"),
        ):
            get_llm_chat_client()

    def test_raises_when_api_key_missing(self):
        mock_settings = MagicMock()
        mock_settings.llm_base_url = "https://example.openai.azure.com"
        mock_settings.llm_api_key = ""
        with (
            patch(
                "core.llm_client.get_settings",
                autospec=True,
                return_value=mock_settings,
            ),
            pytest.raises(LLMClientError, match="not configured"),
        ):
            get_llm_chat_client()

    def test_error_is_not_retriable(self):
        mock_settings = MagicMock()
        mock_settings.llm_base_url = ""
        mock_settings.llm_api_key = ""
        with patch(
            "core.llm_client.get_settings",
            autospec=True,
            return_value=mock_settings,
        ):
            with pytest.raises(LLMClientError) as exc_info:
                get_llm_chat_client()
            assert exc_info.value.retriable is False

    def test_creates_client_when_configured(self):
        mock_settings = MagicMock()
        mock_settings.llm_base_url = "https://example.openai.azure.com"
        mock_settings.llm_api_key = "test-key"
        mock_settings.llm_model = "gpt-5-mini"
        mock_settings.llm_api_version = "2024-10-21"
        mock_client_instance = MagicMock()

        with (
            patch(
                "core.llm_client.get_settings",
                autospec=True,
                return_value=mock_settings,
            ),
            patch(
                "agent_framework.azure.AzureOpenAIChatClient",
                autospec=True,
                return_value=mock_client_instance,
            ) as MockClient,
        ):
            result = get_llm_chat_client()

        MockClient.assert_called_once_with(
            endpoint="https://example.openai.azure.com",
            deployment_name="gpt-5-mini",
            api_key="test-key",
            api_version="2024-10-21",
        )
        assert result is mock_client_instance

    def test_returns_cached_instance(self):
        import core.llm_client as mod

        sentinel = MagicMock()
        mod._llm_client = sentinel
        assert get_llm_chat_client() is sentinel

    def test_default_model_when_not_set(self):
        mock_settings = MagicMock()
        mock_settings.llm_base_url = "https://example.openai.azure.com"
        mock_settings.llm_api_key = "test-key"
        mock_settings.llm_model = ""
        mock_settings.llm_api_version = ""

        with (
            patch(
                "core.llm_client.get_settings",
                autospec=True,
                return_value=mock_settings,
            ),
            patch(
                "agent_framework.azure.AzureOpenAIChatClient",
                autospec=True,
            ) as MockClient,
        ):
            get_llm_chat_client()

        call_kwargs = MockClient.call_args[1]
        assert call_kwargs["deployment_name"] == "gpt-5-mini"
        assert call_kwargs["api_version"] == "2024-10-21"
```

---

## File 4: Extend `api/tests/core/test_cache.py`

Add `TestUserCache` class and update fixture to also clear `_user_cache`.

**Changes to imports** (add 4 imports):
```python
from core.cache import (
    _user_cache,
    get_cached_user,
    invalidate_user_cache,
    set_cached_user,
    # ...existing imports...
)
```

**Changes to `_clear_caches` fixture** (add 2 lines):
```python
@pytest.fixture(autouse=True)
def _clear_caches():
    _progress_cache.clear()
    _phase_detail_cache.clear()
    _user_cache.clear()          # ADD
    yield
    _progress_cache.clear()
    _phase_detail_cache.clear()
    _user_cache.clear()          # ADD
```

**New test class** (append at end of file):
```python
@pytest.mark.unit
class TestUserCache:
    """Test user cache get/set/invalidate."""

    def test_set_and_get(self):
        mock_user = MagicMock()
        set_cached_user(1, mock_user)
        assert get_cached_user(1) is mock_user

    def test_get_returns_none_when_not_cached(self):
        assert get_cached_user(999) is None

    def test_invalidate_clears_user(self):
        mock_user = MagicMock()
        set_cached_user(1, mock_user)
        invalidate_user_cache(1)
        assert get_cached_user(1) is None

    def test_invalidate_noop_when_not_cached(self):
        invalidate_user_cache(999)  # Should not raise
```

---

## File 5: Extend `api/tests/test_logger.py`

Add `TestRequestContextFilter` class.

**Changes to imports** (add 1 import):
```python
from core.logger import _JSONFormatter, _RequestContextFilter, configure_logging
```

**New test class** (append at end of file):
```python
@pytest.mark.unit
class TestRequestContextFilter:
    """Test _RequestContextFilter injects github_username from context var."""

    def test_injects_username_from_context_var(self):
        from core.middleware import request_github_username

        token = request_github_username.set("testuser")
        try:
            f = _RequestContextFilter()
            record = logging.LogRecord(
                "test", logging.INFO, "", 0, "msg", (), None
            )
            f.filter(record)
            assert record.github_username == "testuser"
        finally:
            request_github_username.reset(token)

    def test_does_not_overwrite_explicit_username(self):
        from core.middleware import request_github_username

        token = request_github_username.set("ctx-user")
        try:
            f = _RequestContextFilter()
            record = logging.LogRecord(
                "test", logging.INFO, "", 0, "msg", (), None
            )
            record.github_username = "explicit-user"
            f.filter(record)
            assert record.github_username == "explicit-user"
        finally:
            request_github_username.reset(token)

    def test_no_username_when_context_var_empty(self):
        f = _RequestContextFilter()
        record = logging.LogRecord(
            "test", logging.INFO, "", 0, "msg", (), None
        )
        f.filter(record)
        assert not getattr(record, "github_username", None)
```

---

## Trade-offs

### 1. Direct `Settings()` construction vs `monkeypatch.setenv` + `get_settings()`

- **Chosen**: Direct construction for validation tests (explicit, no env leakage); `monkeypatch` only for `get_settings()` / `clear_settings_cache()` tests.
- **Rejected**: All-`monkeypatch` — too fragile, `.env` file can interfere, and testing the validator doesn't require the `lru_cache` path.

### 2. Real `httpx.AsyncClient` vs mock

- **Chosen**: Real client in `test_github_client.py` — it's a real singleton test, and `httpx.AsyncClient` is cheap to create. Teardown fixture closes it.
- **Rejected**: Mocking httpx — would test nothing (just that mock returns mock).

### 3. Mocking `AzureOpenAIChatClient` in `test_llm_client.py`

- **Chosen**: Mock via `patch("agent_framework.azure.AzureOpenAIChatClient")` — the import happens inside the function body, so patching at the real module path works.
- **Rejected**: Importing the real class — would require Azure credentials and make tests slow/flaky.

### 4. Modules skipped

- **`metrics.py`** (7 lines) — OTel counter/histogram declarations. No-op when telemetry disabled. Testing would just assert `create_counter()` was called.
- **`observability.py`** (85 lines) — Pure OTel SDK wiring. Would require mocking every OTel class. Fragile, zero business value.
- **`templates.py`** (4 lines) — `Jinja2Templates(directory=...)`. One line of config.

---

## Risks & Edge Cases

| Risk | Mitigation |
|------|-----------|
| `Settings()` reads `.env` file — could pick up dev settings | Tests construct `Settings` with explicit args; `extra="ignore"` drops unknowns. For `get_settings()` tests, `monkeypatch.setenv` controls values. |
| `github_client` global state leaks between tests | `autouse` async fixture closes and nullifies `_github_http_client` after every test. |
| `llm_client` `_llm_client` global leaks between tests | `autouse` fixture sets `mod._llm_client = None` before and after every test. |
| `_RequestContextFilter` context var leaks | Each test manually `set()` / `reset()` the context var token in `try/finally`. |
| `Settings.content_dir_path` uses `__file__` reference | Test asserts the *shape* (`name == "phases"`, `"content" in parts`), not an absolute path. |
| `get_settings()` `lru_cache` caching stale values | `autouse` fixture calls `clear_settings_cache()` before and after each test. |

---

## Todo List

- [x] **Phase 1: test_config.py** — Create `api/tests/core/test_config.py` (18 tests) ✅
  - [x] `TestSettingsValidation` — debug allows defaults, requires DB, azure postgres works, prod requires github, prod requires secret, prod accepts valid
  - [x] `TestUseAzurePostgres` — true when both set, false when host missing, false when user missing
  - [x] `TestContentDirPath` — custom path, default fallback
  - [x] `TestAllowedOrigins` — debug localhost, prod no localhost, frontend_url, CSV parse, dedup
  - [x] `TestGetSettings` — same instance, clear resets
- [x] **Phase 2: test_github_client.py** — Create `api/tests/core/test_github_client.py` (6 tests) ✅
  - [x] `TestGetGitHubClient` — creates on first call, returns same instance, recreates after close
  - [x] `TestCloseGitHubClient` — closes client, noop when None, sets global to None
- [x] **Phase 3: test_llm_client.py** — Create `api/tests/core/test_llm_client.py` (9 tests) ✅
  - [x] `TestLLMClientError` — defaults, retriable, message
  - [x] `TestGetLLMChatClient` — raises when unconfigured (2 variants), not retriable, creates when configured, cached, default model
- [x] **Phase 4: Extend test_cache.py** — Add `TestUserCache` to existing file (4 tests) ✅
  - [x] Add `_user_cache` import and clear to fixture
  - [x] `TestUserCache` — set/get, returns none, invalidate, noop invalidate
- [x] **Phase 5: Extend test_logger.py** — Add `TestRequestContextFilter` to existing file (3 tests) ✅
  - [x] Add `_RequestContextFilter` import
  - [x] `TestRequestContextFilter` — injects from context var, doesn't overwrite explicit, empty context var
- [x] **Final: Run full core test suite** — 122 passed in 0.74s ✅
