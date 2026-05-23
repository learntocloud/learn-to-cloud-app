"""Unit tests for the split Settings classes.

Tests cover:
- DatabaseSettings / WorkerSettings / WebSettings validation per profile
- Environment enum behavior (development vs production)
- use_azure_postgres property (on the DB base class)
- content_dir_path computed property (on the worker class)
- allowed_origins computed property (on the web class) with deduplication
- configure_settings / get_*_settings registry + clear_settings_cache
"""

import pytest
from pydantic import ValidationError

from learn_to_cloud_shared.core.config import (
    DatabaseSettings,
    Environment,
    WebSettings,
    WorkerSettings,
    clear_settings_cache,
    configure_settings,
    get_database_settings,
    get_web_settings,
    get_worker_settings,
)


@pytest.fixture(autouse=True)
def _reset_registry():
    """Reset the module-level registry between tests."""
    clear_settings_cache()
    configure_settings(WebSettings)  # restore default after every test
    yield
    clear_settings_cache()
    configure_settings(WebSettings)


# ---------------------------------------------------------------------------
# DatabaseSettings — the minimal class
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestDatabaseSettings:
    def test_accepts_database_url(self):
        s = DatabaseSettings(database_url="postgresql+asyncpg://localhost/test")
        assert s.database_url == "postgresql+asyncpg://localhost/test"

    def test_requires_database_config(self, monkeypatch: pytest.MonkeyPatch):
        # The test conftest sets DATABASE_URL — bypass it to exercise the validator.
        monkeypatch.delenv("DATABASE_URL", raising=False)
        monkeypatch.delenv("POSTGRES_HOST", raising=False)
        monkeypatch.delenv("POSTGRES_USER", raising=False)
        with pytest.raises(ValidationError, match="Database configuration"):
            DatabaseSettings(_env_file=None)  # type: ignore[call-arg]

    def test_azure_postgres_satisfies_database_requirement(self):
        s = DatabaseSettings(
            database_url="",
            postgres_host="myhost.postgres.database.azure.com",
            postgres_user="myuser",
        )
        assert s.use_azure_postgres is True


# ---------------------------------------------------------------------------
# WorkerSettings
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestWorkerSettings:
    def test_inherits_database_validation(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.delenv("DATABASE_URL", raising=False)
        monkeypatch.delenv("POSTGRES_HOST", raising=False)
        monkeypatch.delenv("POSTGRES_USER", raising=False)
        with pytest.raises(ValidationError, match="Database configuration"):
            WorkerSettings(_env_file=None)  # type: ignore[call-arg]

    def test_accepts_worker_fields(self):
        s = WorkerSettings(
            database_url="postgresql+asyncpg://localhost/test",
            github_token="ghp_xxx",
            labs_verification_secret="secret",
        )
        assert s.github_token == "ghp_xxx"
        assert s.labs_verification_secret == "secret"

    def test_no_oauth_validation(self):
        # Worker MUST be allowed to start without web-only OAuth creds.
        # The validator on WebSettings doesn't exist on WorkerSettings,
        # so this simply needs to construct successfully.
        WorkerSettings(database_url="postgresql+asyncpg://localhost/test")


# ---------------------------------------------------------------------------
# WebSettings — environment-driven validation
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestWebSettingsValidation:
    def test_development_allows_defaults(self):
        s = WebSettings(
            database_url="postgresql+asyncpg://localhost/test",
            environment="development",
        )
        assert s.environment is Environment.DEVELOPMENT
        assert s.is_development is True

    def test_development_does_not_require_oauth(self):
        s = WebSettings(
            database_url="postgresql+asyncpg://localhost/test",
            environment="development",
        )
        assert s.github_client_id == ""

    def test_production_requires_github_credentials(self):
        with pytest.raises(ValidationError, match="GITHUB_CLIENT_ID"):
            WebSettings(
                database_url="postgresql+asyncpg://localhost/test",
                environment="production",
                github_client_id="",
                github_client_secret="",
            )

    def test_production_requires_session_secret(self):
        with pytest.raises(ValidationError, match="SESSION_SECRET_KEY"):
            WebSettings(
                database_url="postgresql+asyncpg://localhost/test",
                environment="production",
                github_client_id="id",
                github_client_secret="secret",
                # Default session secret should be rejected in production
            )

    def test_production_accepts_valid_config(self):
        s = WebSettings(
            database_url="postgresql+asyncpg://localhost/test",
            environment="production",
            github_client_id="id",
            github_client_secret="secret",
            session_secret_key="a-real-secret-not-the-default",
        )
        assert s.environment is Environment.PRODUCTION
        assert s.is_development is False


# ---------------------------------------------------------------------------
# content_dir_path (lives on WorkerSettings, available on WebSettings via MRO)
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestContentDirPath:
    def test_custom_path_from_setting(self):
        s = WebSettings(
            database_url="postgresql+asyncpg://localhost/db",
            environment="development",
            content_dir="/custom/path",
        )
        assert s.content_dir_path.as_posix() == "/custom/path"

    def test_default_fallback(self):
        s = WebSettings(
            database_url="postgresql+asyncpg://localhost/db",
            environment="development",
        )
        assert s.content_dir_path.name == "phases"
        assert "content" in s.content_dir_path.parts


# ---------------------------------------------------------------------------
# Frontend telemetry
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestFrontendTelemetryConfig:
    def test_defaults_to_disabled(self):
        s = WebSettings(
            database_url="postgresql+asyncpg://localhost/db",
            environment="development",
        )
        assert s.frontend_applicationinsights_connection_string == ""
        assert s.frontend_telemetry_sampling_percentage == 100.0

    def test_accepts_frontend_connection_string(self):
        conn_str = "InstrumentationKey=abc;IngestionEndpoint=https://example.invalid/"
        s = WebSettings(
            database_url="postgresql+asyncpg://localhost/db",
            environment="development",
            frontend_applicationinsights_connection_string=conn_str,
        )
        assert s.frontend_applicationinsights_connection_string == conn_str

    def test_rejects_invalid_frontend_telemetry_sampling_percentage(self):
        with pytest.raises(ValidationError):
            WebSettings(
                database_url="postgresql+asyncpg://localhost/db",
                environment="development",
                frontend_telemetry_sampling_percentage=101,
            )


# ---------------------------------------------------------------------------
# allowed_origins
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestAllowedOrigins:
    def test_development_includes_localhost(self):
        s = WebSettings(
            database_url="postgresql+asyncpg://localhost/db",
            environment="development",
        )
        assert "http://localhost:3000" in s.allowed_origins
        assert "http://localhost:4280" in s.allowed_origins

    def test_production_excludes_localhost(self):
        s = WebSettings(
            database_url="postgresql+asyncpg://localhost/db",
            environment="production",
            github_client_id="id",
            github_client_secret="secret",
            session_secret_key="prod-secret",
        )
        assert "http://localhost:3000" not in s.allowed_origins

    def test_frontend_url_included(self):
        s = WebSettings(
            database_url="postgresql+asyncpg://localhost/db",
            environment="development",
            frontend_url="https://app.example.com",
        )
        assert "https://app.example.com" in s.allowed_origins

    def test_cors_allowed_origins_csv_parsed(self):
        s = WebSettings(
            database_url="postgresql+asyncpg://localhost/db",
            environment="development",
            cors_allowed_origins="https://a.com, https://b.com",
        )
        assert "https://a.com" in s.allowed_origins
        assert "https://b.com" in s.allowed_origins

    def test_deduplication(self):
        s = WebSettings(
            database_url="postgresql+asyncpg://localhost/db",
            environment="development",
            frontend_url="http://localhost:4280",
        )
        assert s.allowed_origins.count("http://localhost:4280") == 1


# ---------------------------------------------------------------------------
# Registry — configure_settings + get_*_settings + clear_settings_cache
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestSettingsRegistry:
    def test_get_database_settings_works_with_web_default(self):
        # The autouse fixture configures WebSettings; WebSettings ISA DatabaseSettings
        s = get_database_settings()
        assert isinstance(s, DatabaseSettings)

    def test_get_worker_settings_requires_worker_or_web_profile(self):
        configure_settings(DatabaseSettings)
        with pytest.raises(RuntimeError, match="WorkerSettings"):
            get_worker_settings()

    def test_get_web_settings_requires_web_profile(self):
        configure_settings(WorkerSettings)
        with pytest.raises(RuntimeError, match="WebSettings"):
            get_web_settings()

    def test_clear_cache_allows_reconfiguration(self):
        configure_settings(WebSettings)
        get_database_settings()  # constructs WebSettings
        clear_settings_cache()
        configure_settings(DatabaseSettings)
        s = get_database_settings()
        assert type(s) is DatabaseSettings

    def test_configure_more_specific_after_construction_raises(self):
        # Worker instance exists; configuring WebSettings (more specific —
        # would need OAuth validation Worker never ran) must raise.
        configure_settings(WorkerSettings)
        get_database_settings()  # constructs WorkerSettings
        with pytest.raises(RuntimeError, match="configure_settings"):
            configure_settings(WebSettings)

    def test_configure_less_specific_after_construction_is_noop(self):
        # Web instance exists; configuring DatabaseSettings (less specific)
        # is fine because WebSettings already satisfies the DB-only request.
        configure_settings(WebSettings)
        get_database_settings()  # constructs WebSettings
        configure_settings(DatabaseSettings)  # should NOT raise
