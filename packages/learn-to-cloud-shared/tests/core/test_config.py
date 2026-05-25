"""Unit tests for composed Settings classes."""

import pytest
from pydantic import ValidationError

from learn_to_cloud_shared.core.config import (
    ContentConfig,
    CorsConfig,
    DatabaseConfig,
    Environment,
    FrontendTelemetryConfig,
    GitHubConfig,
    LabsConfig,
    MigrationSettings,
    OAuthConfig,
    SessionConfig,
    WebSecurityConfig,
    WebSettings,
    WorkerSettings,
    clear_settings_cache,
    get_web_settings,
)


@pytest.fixture(autouse=True)
def _reset_settings_cache():
    clear_settings_cache()
    yield
    clear_settings_cache()


@pytest.mark.unit
class TestDatabaseConfig:
    def test_accepts_database_url(self):
        s = DatabaseConfig(url="postgresql+asyncpg://localhost/test")
        assert s.url == "postgresql+asyncpg://localhost/test"

    def test_requires_database_config(self):
        with pytest.raises(ValidationError, match="Database configuration"):
            DatabaseConfig()

    def test_azure_postgres_satisfies_database_requirement(self):
        s = DatabaseConfig(
            url="",
            host="myhost.postgres.database.azure.com",
            user="myuser",
        )
        assert s.use_azure_postgres is True


@pytest.mark.unit
class TestWorkerSettings:
    def test_accepts_worker_sections(self):
        s = WorkerSettings(
            database=DatabaseConfig(url="postgresql+asyncpg://localhost/test"),
            github=GitHubConfig(token="ghp_xxx"),
            labs=LabsConfig(verification_secret="secret"),
        )
        assert s.github.token == "ghp_xxx"
        assert s.labs.verification_secret == "secret"

    def test_no_oauth_validation(self):
        WorkerSettings(
            database=DatabaseConfig(url="postgresql+asyncpg://localhost/test")
        )


@pytest.mark.unit
class TestWebSettingsValidation:
    def test_development_allows_defaults(self):
        s = WebSettings(
            database=DatabaseConfig(url="postgresql+asyncpg://localhost/test"),
            environment="development",
        )
        assert s.environment is Environment.DEVELOPMENT
        assert s.is_development is True

    def test_development_does_not_require_oauth(self):
        s = WebSettings(
            database=DatabaseConfig(url="postgresql+asyncpg://localhost/test"),
            environment="development",
        )
        assert s.oauth.client_id == ""

    def test_production_requires_github_credentials(self):
        with pytest.raises(ValidationError, match="OAUTH__CLIENT_ID"):
            WebSettings(
                database=DatabaseConfig(url="postgresql+asyncpg://localhost/test"),
                environment="production",
                oauth=OAuthConfig(client_id="", client_secret=""),
            )

    def test_production_requires_session_secret(self):
        with pytest.raises(ValidationError, match="SESSION__SECRET_KEY"):
            WebSettings(
                database=DatabaseConfig(url="postgresql+asyncpg://localhost/test"),
                environment="production",
                oauth=OAuthConfig(client_id="id", client_secret="secret"),
            )

    def test_production_accepts_valid_config(self):
        s = WebSettings(
            database=DatabaseConfig(url="postgresql+asyncpg://localhost/test"),
            environment="production",
            oauth=OAuthConfig(client_id="id", client_secret="secret"),
            session=SessionConfig(secret_key="a-real-secret-not-the-default"),
        )
        assert s.environment is Environment.PRODUCTION
        assert s.is_development is False


@pytest.mark.unit
class TestContentDirPath:
    def test_custom_path_from_setting(self):
        s = ContentConfig(dir="/custom/path")
        assert s.dir_path.as_posix() == "/custom/path"

    def test_default_fallback(self):
        s = ContentConfig()
        assert s.dir_path.name == "phases"
        assert "content" in s.dir_path.parts


@pytest.mark.unit
class TestFrontendTelemetryConfig:
    def test_defaults_to_disabled(self):
        s = FrontendTelemetryConfig()
        assert s.applicationinsights_connection_string == ""
        assert s.sampling_percentage == 100.0

    def test_accepts_frontend_connection_string(self):
        conn_str = "InstrumentationKey=abc;IngestionEndpoint=https://example.invalid/"
        s = FrontendTelemetryConfig(applicationinsights_connection_string=conn_str)
        assert s.applicationinsights_connection_string == conn_str

    def test_rejects_invalid_frontend_telemetry_sampling_percentage(self):
        with pytest.raises(ValidationError):
            FrontendTelemetryConfig(sampling_percentage=101)


@pytest.mark.unit
class TestAllowedOrigins:
    def test_development_includes_localhost(self):
        s = WebSettings(
            database=DatabaseConfig(url="postgresql+asyncpg://localhost/db"),
            environment="development",
        )
        assert "http://localhost:3000" in s.allowed_origins
        assert "http://localhost:4280" in s.allowed_origins

    def test_production_excludes_localhost(self):
        s = WebSettings(
            database=DatabaseConfig(url="postgresql+asyncpg://localhost/db"),
            environment="production",
            oauth=OAuthConfig(client_id="id", client_secret="secret"),
            session=SessionConfig(secret_key="prod-secret"),
        )
        assert "http://localhost:3000" not in s.allowed_origins

    def test_frontend_url_included(self):
        s = WebSettings(
            database=DatabaseConfig(url="postgresql+asyncpg://localhost/db"),
            environment="development",
            cors=CorsConfig(frontend_url="https://app.example.com"),
        )
        assert any(o == "https://app.example.com" for o in s.allowed_origins)

    def test_cors_allowed_origins_csv_parsed(self):
        s = WebSettings(
            database=DatabaseConfig(url="postgresql+asyncpg://localhost/db"),
            environment="development",
            cors=CorsConfig(allowed_origins="https://a.com, https://b.com"),
        )
        assert any(o == "https://a.com" for o in s.allowed_origins)
        assert any(o == "https://b.com" for o in s.allowed_origins)

    def test_deduplication(self):
        s = WebSettings(
            database=DatabaseConfig(url="postgresql+asyncpg://localhost/db"),
            environment="development",
            cors=CorsConfig(frontend_url="http://localhost:4280"),
        )
        assert s.allowed_origins.count("http://localhost:4280") == 1


@pytest.mark.unit
class TestFlatEnvCompatibility:
    def test_old_database_url_populates_nested_database(
        self, monkeypatch: pytest.MonkeyPatch
    ):
        monkeypatch.delenv("DATABASE__URL", raising=False)
        s = MigrationSettings(database_url="postgresql+asyncpg://localhost/db")
        assert s.database.url == "postgresql+asyncpg://localhost/db"

    def test_new_nested_database_wins_over_old_flat_database_url(self):
        s = MigrationSettings(
            database=DatabaseConfig(url="postgresql+asyncpg://localhost/new"),
            database_url="postgresql+asyncpg://localhost/old",
        )
        assert s.database.url == "postgresql+asyncpg://localhost/new"

    def test_old_web_flat_fields_populate_nested_sections(
        self, monkeypatch: pytest.MonkeyPatch
    ):
        monkeypatch.delenv("DATABASE__URL", raising=False)
        s = WebSettings(
            database_url="postgresql+asyncpg://localhost/db",
            environment="production",
            github_client_id="id",
            github_client_secret="secret",
            session_secret_key="prod-secret",
            require_https=False,
        )
        assert s.database.url == "postgresql+asyncpg://localhost/db"
        assert s.oauth.client_id == "id"
        assert s.session.secret_key == "prod-secret"
        assert s.web_security.require_https is False


@pytest.mark.unit
class TestSettingsFactories:
    def test_get_web_settings_is_cached(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setenv("DATABASE_URL", "postgresql+asyncpg://localhost/db")
        monkeypatch.setenv("ENVIRONMENT", "development")
        clear_settings_cache()
        assert get_web_settings() is get_web_settings()

    def test_clear_settings_cache_reloads_environment(
        self, monkeypatch: pytest.MonkeyPatch
    ):
        monkeypatch.delenv("DATABASE__URL", raising=False)
        monkeypatch.setenv("DATABASE_URL", "postgresql+asyncpg://localhost/one")
        monkeypatch.setenv("ENVIRONMENT", "development")
        clear_settings_cache()
        assert get_web_settings().database.url.endswith("/one")

        monkeypatch.setenv("DATABASE_URL", "postgresql+asyncpg://localhost/two")
        clear_settings_cache()
        assert get_web_settings().database.url.endswith("/two")


@pytest.mark.unit
class TestWebSecurityConfig:
    def test_require_https_can_be_disabled(self):
        s = WebSecurityConfig(require_https=False)
        assert s.require_https is False
