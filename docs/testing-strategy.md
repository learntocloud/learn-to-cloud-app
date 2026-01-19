# Testing Strategy

## Settings Configuration in Tests

This project uses direct `get_settings()` calls for configuration access (not FastAPI dependency injection). This follows the pattern used in [tiangolo's official FastAPI template](https://github.com/fastapi/full-stack-fastapi-template).

### Why Direct Calls?

| Approach | Where it works | Consistency |
|----------|----------------|-------------|
| `Depends(get_settings)` | Routes only | ❌ Services can't use it |
| `get_settings()` direct | Everywhere | ✅ Same pattern in all layers |

Since services, utilities, and background tasks cannot use FastAPI's `Depends()`, we use direct calls everywhere for consistency.

### Overriding Settings in Tests

#### Option 1: Environment Variables (Recommended)

Use pytest's `monkeypatch` fixture to set environment variables before clearing the settings cache:

```python
import pytest
from core.config import get_settings, clear_settings_cache


@pytest.fixture
def test_settings(monkeypatch):
    """Configure test environment settings."""
    monkeypatch.setenv("ENVIRONMENT", "test")
    monkeypatch.setenv("DATABASE_URL", "postgresql+asyncpg://postgres:postgres@localhost:5432/test_db")
    monkeypatch.setenv("CTF_MASTER_SECRET", "test-secret-for-ctf")
    clear_settings_cache()
    yield get_settings()
    clear_settings_cache()  # Clean up after test


def test_something(test_settings):
    assert test_settings.environment == "test"
```

#### Option 2: Patching get_settings (For Mocking)

When you need complete control over settings values:

```python
from unittest.mock import patch
from core.config import Settings


def test_with_mock_settings():
    mock_settings = Settings(
        database_url="postgresql+asyncpg://test:test@localhost/test",
        environment="test",
        ctf_master_secret="test-secret",
    )

    with patch("services.my_service.get_settings", return_value=mock_settings):
        # Test code that uses get_settings() in my_service
        result = my_service.do_something()
        assert result == expected
```

#### Option 3: Patching Specific Attributes

For simple attribute overrides:

```python
from unittest.mock import patch


def test_with_patched_attribute():
    with patch("core.config.get_settings") as mock:
        mock.return_value.environment = "production"
        mock.return_value.google_api_key = "fake-key"

        # Test code
        ...
```

### Testing FastAPI Routes

For integration tests with the FastAPI test client:

```python
import pytest
from fastapi.testclient import TestClient
from core.config import clear_settings_cache


@pytest.fixture
def client(monkeypatch):
    """Create test client with test settings."""
    monkeypatch.setenv("ENVIRONMENT", "test")
    monkeypatch.setenv("DATABASE_URL", "postgresql+asyncpg://postgres:postgres@localhost:5432/test_db")
    monkeypatch.setenv("CTF_MASTER_SECRET", "test-secret")
    clear_settings_cache()

    from main import app
    return TestClient(app)


def test_health_endpoint(client):
    response = client.get("/health")
    assert response.status_code == 200
```

### Key Functions

| Function | Purpose |
|----------|---------|
| `get_settings()` | Get cached Settings instance |
| `clear_settings_cache()` | Reset cache (call after changing env vars) |

### Best Practices

1. **Always call `clear_settings_cache()`** after modifying environment variables
2. **Use fixtures** to ensure cleanup happens even if tests fail
3. **Prefer environment variables** over mocking for realistic tests
4. **Mock at the import site** when patching (e.g., `services.my_service.get_settings`)

### DI Strategy Summary

This codebase follows a clear pattern:

| Component Type | Uses DI (`Depends`)? | Example |
|----------------|---------------------|---------|
| Auth (cross-cutting) | ✅ Yes | `get_current_user` |
| Database session | ✅ Yes | `get_db_session` |
| Settings | ❌ No | `get_settings()` |
| Services | ❌ No | Direct function calls |
| Utilities | ❌ No | Direct function calls |

**Rule**: Use DI for cross-cutting concerns and external resources. Use direct calls for internal configuration and layer composition.
