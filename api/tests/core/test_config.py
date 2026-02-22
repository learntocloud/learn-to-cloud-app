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
                github_client_id="",
                github_client_secret="",
            )

    def test_prod_requires_session_secret(self):
        with pytest.raises(ValidationError, match="SESSION_SECRET_KEY"):
            Settings(
                database_url="postgresql+asyncpg://localhost/test",
                debug=False,
                github_client_id="id",
                github_client_secret="secret",
                session_secret_key="dev-secret-key-change-in-production",
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
