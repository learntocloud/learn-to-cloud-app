"""Application configuration split by runtime profile."""

from __future__ import annotations

from enum import StrEnum
from functools import lru_cache
from importlib.resources import files
from pathlib import Path
from typing import Any, Self

from pydantic import BaseModel, Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Environment(StrEnum):
    """Runtime environment for the webapp."""

    DEVELOPMENT = "development"
    PRODUCTION = "production"


_DEV_SESSION_SECRET = "dev-secret-key-change-in-production"

_SETTINGS_CONFIG = SettingsConfigDict(
    env_file=".env",
    env_file_encoding="utf-8",
    env_nested_delimiter="__",
    nested_model_default_partial_update=True,
    extra="ignore",
    frozen=True,
)


def _load_from_environment[SettingsT: BaseSettings](
    settings_type: type[SettingsT],
) -> SettingsT:
    values: dict[str, Any] = {}
    return settings_type(**values)


class FrozenConfig(BaseModel):
    """Immutable nested config base."""

    model_config = {"frozen": True}


class DatabaseConfig(FrozenConfig):
    """Database connection, pool, and timeout config."""

    url: str = ""

    # Azure PostgreSQL with Managed Identity takes precedence over url.
    host: str = ""
    port: int = 5432
    name: str = "learntocloud"
    user: str = ""

    timeout: int = 30
    pool_size: int = 5
    pool_max_overflow: int = 5
    pool_timeout: int = 30
    pool_recycle: int = 1800
    statement_timeout_ms: int = 10000
    echo: bool = False

    @model_validator(mode="after")
    def _validate_database(self) -> Self:
        if not self.url and not self.use_azure_postgres:
            raise ValueError(
                "Database configuration required. "
                "Set DATABASE__URL for direct connection, "
                "or DATABASE__HOST + DATABASE__USER for Azure Managed Identity."
            )
        return self

    @property
    def use_azure_postgres(self) -> bool:
        """When True, connection is built from Azure PostgreSQL fields."""
        return bool(self.host and self.user)


class GitHubConfig(FrozenConfig):
    """Server-to-server GitHub API access."""

    token: str = ""


class LabsConfig(FrozenConfig):
    """Lab verification config."""

    verification_secret: str = ""


class HttpConfig(FrozenConfig):
    """Shared outbound HTTP config."""

    external_api_timeout: float = 15.0


class ContentConfig(FrozenConfig):
    """Authored curriculum content config."""

    dir: str = ""

    @property
    def dir_path(self) -> Path:
        """Resolve authored curriculum YAML for sync and validation jobs."""
        if self.dir:
            return Path(self.dir)

        source_content = Path(
            str(files("learn_to_cloud_shared").joinpath("content", "phases"))
        )
        if source_content.exists():
            return source_content

        raise RuntimeError(
            "CONTENT__DIR is required because curriculum YAML is not packaged "
            "with learn-to-cloud-shared. Set CONTENT__DIR to the copied "
            "content/phases directory in jobs that sync or validate YAML."
        )


class OAuthConfig(FrozenConfig):
    """User-facing GitHub OAuth config."""

    client_id: str = ""
    client_secret: str = ""


class SessionConfig(FrozenConfig):
    """Session cookie config."""

    secret_key: str = _DEV_SESSION_SECRET


class CorsConfig(FrozenConfig):
    """Frontend URL and CORS config."""

    allowed_origins: str = ""
    frontend_url: str = "http://localhost:4280"

    def origin_list(self, *, is_development: bool) -> list[str]:
        """Combine localhost, frontend_url, and CSV configured origins."""
        origins: list[str] = []

        if is_development:
            origins.extend(
                [
                    "http://localhost:3000",
                    "http://localhost:4280",
                ]
            )

        if self.frontend_url and self.frontend_url not in origins:
            origins.append(self.frontend_url)

        if self.allowed_origins:
            for origin in self.allowed_origins.split(","):
                origin = origin.strip()
                if origin and origin not in origins:
                    origins.append(origin)

        return origins


class FrontendTelemetryConfig(FrozenConfig):
    """Frontend telemetry config exposed to templates."""

    applicationinsights_connection_string: str = ""
    sampling_percentage: float = Field(default=100.0, ge=0.0, le=100.0)


class VerificationFunctionsConfig(FrozenConfig):
    """Durable verification Functions starter config."""

    base_url: str = ""
    key: str = ""


class RateLimitConfig(FrozenConfig):
    """Rate-limit storage config."""

    # memory:// only works for single-instance deployments.
    storage_uri: str = "memory://"


class WebSecurityConfig(FrozenConfig):
    """Web security and documentation toggles."""

    require_https: bool = True
    enable_docs: bool = False


def _nested_missing(data: dict[str, Any], section: str, field: str) -> bool:
    value = data.get(section)
    return not isinstance(value, dict) or value.get(field) in (None, "")


def _copy_flat(data: dict[str, Any], *, flat: str, section: str, field: str) -> None:
    value = data.get(flat)
    if value in (None, "") or not _nested_missing(data, section, field):
        return
    nested = data.setdefault(section, {})
    if isinstance(nested, dict):
        nested[field] = value


def _apply_flat_compat(data: dict[str, Any]) -> dict[str, Any]:
    for flat, section, field in (
        ("database_url", "database", "url"),
        ("postgres_host", "database", "host"),
        ("postgres_port", "database", "port"),
        ("postgres_database", "database", "name"),
        ("postgres_user", "database", "user"),
        ("db_timeout", "database", "timeout"),
        ("db_pool_size", "database", "pool_size"),
        ("db_pool_max_overflow", "database", "pool_max_overflow"),
        ("db_pool_timeout", "database", "pool_timeout"),
        ("db_pool_recycle", "database", "pool_recycle"),
        ("db_statement_timeout_ms", "database", "statement_timeout_ms"),
        ("db_echo", "database", "echo"),
        ("github_token", "github", "token"),
        ("labs_verification_secret", "labs", "verification_secret"),
        ("external_api_timeout", "http", "external_api_timeout"),
        ("content_dir", "content", "dir"),
        ("github_client_id", "oauth", "client_id"),
        ("github_client_secret", "oauth", "client_secret"),
        ("session_secret_key", "session", "secret_key"),
        ("cors_allowed_origins", "cors", "allowed_origins"),
        ("frontend_url", "cors", "frontend_url"),
        (
            "frontend_applicationinsights_connection_string",
            "frontend_telemetry",
            "applicationinsights_connection_string",
        ),
        (
            "frontend_telemetry_sampling_percentage",
            "frontend_telemetry",
            "sampling_percentage",
        ),
        (
            "verification_functions_base_url",
            "verification_functions",
            "base_url",
        ),
        ("verification_functions_key", "verification_functions", "key"),
        ("ratelimit_storage_uri", "rate_limit", "storage_uri"),
        ("require_https", "web_security", "require_https"),
        ("enable_docs", "web_security", "enable_docs"),
    ):
        _copy_flat(data, flat=flat, section=section, field=field)
    return data


class _FlatCompatMixin:
    """Temporary flat env var support during the nested settings rollout."""

    database_url: str = Field(default="", exclude=True)
    postgres_host: str = Field(default="", exclude=True)
    postgres_port: int | None = Field(default=None, exclude=True)
    postgres_database: str = Field(default="", exclude=True)
    postgres_user: str = Field(default="", exclude=True)
    db_timeout: int | None = Field(default=None, exclude=True)
    db_pool_size: int | None = Field(default=None, exclude=True)
    db_pool_max_overflow: int | None = Field(default=None, exclude=True)
    db_pool_timeout: int | None = Field(default=None, exclude=True)
    db_pool_recycle: int | None = Field(default=None, exclude=True)
    db_statement_timeout_ms: int | None = Field(default=None, exclude=True)
    db_echo: bool | None = Field(default=None, exclude=True)

    github_token: str = Field(default="", exclude=True)
    labs_verification_secret: str = Field(default="", exclude=True)
    external_api_timeout: float | None = Field(default=None, exclude=True)
    content_dir: str = Field(default="", exclude=True)

    github_client_id: str = Field(default="", exclude=True)
    github_client_secret: str = Field(default="", exclude=True)
    session_secret_key: str = Field(default="", exclude=True)
    cors_allowed_origins: str = Field(default="", exclude=True)
    frontend_url: str = Field(default="", exclude=True)
    frontend_applicationinsights_connection_string: str = Field(
        default="", exclude=True
    )
    frontend_telemetry_sampling_percentage: float | None = Field(
        default=None, exclude=True
    )
    verification_functions_base_url: str = Field(default="", exclude=True)
    verification_functions_key: str = Field(default="", exclude=True)
    ratelimit_storage_uri: str = Field(default="", exclude=True)
    require_https: bool | None = Field(default=None, exclude=True)
    enable_docs: bool | None = Field(default=None, exclude=True)

    @model_validator(mode="before")
    @classmethod
    def _migrate_flat_env(cls, data: Any) -> Any:
        if isinstance(data, dict):
            return _apply_flat_compat(data)
        return data


class MigrationSettings(_FlatCompatMixin, BaseSettings):
    """Settings loaded by Alembic and migration jobs."""

    model_config = _SETTINGS_CONFIG

    database: DatabaseConfig
    content: ContentConfig = ContentConfig()


class WorkerSettings(_FlatCompatMixin, BaseSettings):
    """Settings for background workers and shared verification code."""

    model_config = _SETTINGS_CONFIG

    database: DatabaseConfig
    github: GitHubConfig = GitHubConfig()
    labs: LabsConfig = LabsConfig()
    http: HttpConfig = HttpConfig()
    content: ContentConfig = ContentConfig()


class WebSettings(_FlatCompatMixin, BaseSettings):
    """Settings for the FastAPI webapp."""

    model_config = _SETTINGS_CONFIG

    environment: Environment = Environment.PRODUCTION
    database: DatabaseConfig
    github: GitHubConfig = GitHubConfig()
    labs: LabsConfig = LabsConfig()
    http: HttpConfig = HttpConfig()
    content: ContentConfig = ContentConfig()
    oauth: OAuthConfig = OAuthConfig()
    session: SessionConfig = SessionConfig()
    cors: CorsConfig = CorsConfig()
    frontend_telemetry: FrontendTelemetryConfig = FrontendTelemetryConfig()
    verification_functions: VerificationFunctionsConfig = VerificationFunctionsConfig()
    rate_limit: RateLimitConfig = RateLimitConfig()
    web_security: WebSecurityConfig = WebSecurityConfig()
    startup_timeout: int = 60
    verification_wait_timeout: int = 180

    @model_validator(mode="after")
    def _validate_web(self) -> Self:
        if self.environment is Environment.PRODUCTION:
            if not self.oauth.client_id or not self.oauth.client_secret:
                raise ValueError(
                    "OAUTH__CLIENT_ID and OAUTH__CLIENT_SECRET must be set "
                    "when ENVIRONMENT=production."
                )
            if (
                not self.session.secret_key
                or self.session.secret_key == _DEV_SESSION_SECRET
            ):
                raise ValueError(
                    "SESSION__SECRET_KEY must be set to a secure random value "
                    "when ENVIRONMENT=production."
                )
        return self

    @property
    def is_development(self) -> bool:
        return self.environment is Environment.DEVELOPMENT

    @property
    def allowed_origins(self) -> list[str]:
        return self.cors.origin_list(is_development=self.is_development)


@lru_cache
def get_migration_settings() -> MigrationSettings:
    """Return cached migration settings."""
    return _load_from_environment(MigrationSettings)


@lru_cache
def get_worker_settings() -> WorkerSettings:
    """Return cached worker settings."""
    return _load_from_environment(WorkerSettings)


@lru_cache
def get_web_settings() -> WebSettings:
    """Return cached web settings for FastAPI dependency injection."""
    return _load_from_environment(WebSettings)


def clear_settings_cache() -> None:
    """Clear cached settings instances in tests."""
    get_migration_settings.cache_clear()
    get_worker_settings.cache_clear()
    get_web_settings.cache_clear()
