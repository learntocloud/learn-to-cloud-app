"""Unit tests for composed Settings classes."""

import pytest
from pydantic import ValidationError

from learn_to_cloud.core.config import (
    DatabaseConfig,
    Environment,
    FrontendTelemetryConfig,
    MigrationSettings,
    OAuthConfig,
    SessionConfig,
    VerificationWorkerConfig,
    WebSecurityConfig,
    WebSettings,
    get_web_settings,
)
from tests.support.settings import clear_settings_cache


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

    @pytest.mark.parametrize("settings_type", [WebSettings, MigrationSettings])
    def test_database_profiles_require_database(self, monkeypatch, settings_type):
        for name in ("DATABASE__URL", "DATABASE__HOST", "DATABASE__USER"):
            monkeypatch.delenv(name, raising=False)

        with pytest.raises(ValidationError, match="database"):
            settings_type(_env_file=None)


@pytest.mark.unit
class TestSessionConfig:
    @pytest.mark.parametrize(
        ("field", "invalid"),
        [
            ("oauth_state_max_age_seconds", 0),
            ("idle_timeout_seconds", -1),
            ("absolute_timeout_seconds", 2592001),
        ],
    )
    def test_invalid_durations(self, field, invalid):
        with pytest.raises(ValidationError):
            SessionConfig(**{field: invalid})

    def test_idle_cannot_exceed_absolute(self):
        with pytest.raises(ValidationError, match="must not exceed"):
            SessionConfig(idle_timeout_seconds=20, absolute_timeout_seconds=10)

    def test_environment_overrides(self, monkeypatch):
        monkeypatch.setenv("SESSION__IDLE_TIMEOUT_SECONDS", "60")
        monkeypatch.setenv("SESSION__ABSOLUTE_TIMEOUT_SECONDS", "120")
        monkeypatch.setenv("SESSION__OAUTH_STATE_MAX_AGE_SECONDS", "90")
        settings = WebSettings(
            database=DatabaseConfig(url="postgresql+asyncpg://localhost/test"),
            environment=Environment.DEVELOPMENT,
        )
        assert settings.session.idle_timeout_seconds == 60
        assert settings.session.absolute_timeout_seconds == 120
        assert settings.session.oauth_state_max_age_seconds == 90


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

    def test_worker_limits_must_be_positive(self):
        with pytest.raises(ValidationError):
            VerificationWorkerConfig(poll_interval_seconds=0)


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
    def test_development_includes_localhost_and_production_excludes_it(self):
        dev = WebSettings(
            database=DatabaseConfig(url="postgresql+asyncpg://localhost/db"),
            environment="development",
        )
        assert "http://localhost:3000" in dev.allowed_origins
        assert "http://localhost:4280" in dev.allowed_origins

        prod = WebSettings(
            database=DatabaseConfig(url="postgresql+asyncpg://localhost/db"),
            environment="production",
            oauth=OAuthConfig(client_id="id", client_secret="secret"),
            session=SessionConfig(secret_key="prod-secret"),
        )
        assert "http://localhost:3000" not in prod.allowed_origins


@pytest.mark.unit
class TestSettingsFactories:
    def test_clear_settings_cache_reloads_environment(
        self, monkeypatch: pytest.MonkeyPatch
    ):
        monkeypatch.setenv("DATABASE__URL", "postgresql+asyncpg://localhost/one")
        monkeypatch.setenv("ENVIRONMENT", "development")
        clear_settings_cache()
        assert get_web_settings().database.url.endswith("/one")

        monkeypatch.setenv("DATABASE__URL", "postgresql+asyncpg://localhost/two")
        clear_settings_cache()
        assert get_web_settings().database.url.endswith("/two")


@pytest.mark.unit
class TestWebSecurityConfig:
    def test_require_https_can_be_disabled(self):
        s = WebSecurityConfig(require_https=False)
        assert s.require_https is False
