"""Application configuration using pydantic-settings."""

from functools import cached_property, lru_cache
from pathlib import Path
from typing import Self

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        frozen=True,
    )

    database_url: str = ""

    # Azure PostgreSQL with Managed Identity — takes precedence over database_url
    postgres_host: str = ""
    postgres_port: int = 5432
    postgres_database: str = "learntocloud"
    postgres_user: str = ""

    cors_allowed_origins: str = ""

    github_client_id: str = ""
    github_client_secret: str = ""

    session_secret_key: str = "dev-secret-key-change-in-production"

    github_token: str = ""

    labs_verification_secret: str = ""

    http_timeout: float = 10.0

    llm_cli_timeout: int = 120
    code_analysis_cooldown_seconds: int = 3600
    daily_submission_limit: int = 20

    llm_base_url: str = ""
    llm_api_key: str = ""
    llm_model: str = ""
    llm_api_version: str = "2024-10-21"

    # memory:// only works for single-instance deployments
    ratelimit_storage_uri: str = "memory://"

    frontend_url: str = "http://localhost:4280"

    content_dir: str = ""

    # Total connections per worker = pool_size + max_overflow
    db_pool_size: int = 5
    db_pool_max_overflow: int = 5
    db_pool_timeout: int = 30
    db_pool_recycle: int = 300
    db_statement_timeout_ms: int = 10000
    db_echo: bool = False

    debug: bool = False
    require_https: bool = True
    enable_docs: bool = False

    @model_validator(mode="after")
    def validate_config(self) -> Self:
        if not self.database_url and not self.use_azure_postgres:
            raise ValueError(
                "Database configuration required. "
                "Set DATABASE_URL for direct connection, "
                "or POSTGRES_HOST + POSTGRES_USER for Azure Managed Identity."
            )

        # Require auth and security config in production (debug=False)
        if not self.debug:
            if not self.github_client_id or not self.github_client_secret:
                raise ValueError(
                    "GITHUB_CLIENT_ID and GITHUB_CLIENT_SECRET must be set. "
                    "Set DEBUG=true to skip this check in development."
                )
            if self.session_secret_key == "dev-secret-key-change-in-production":
                raise ValueError(
                    "SESSION_SECRET_KEY must be set to a secure random value. "
                    "Set DEBUG=true to skip this check in development."
                )
        return self

    @property
    def use_azure_postgres(self) -> bool:
        """When True, connection built from postgres_* fields instead."""
        return bool(self.postgres_host and self.postgres_user)

    @cached_property
    def content_dir_path(self) -> Path:
        """Defaults to content/phases if CONTENT_DIR not set."""
        if self.content_dir:
            return Path(self.content_dir)
        # Default: assume running from repo root (one level above api/)
        return Path(__file__).parent.parent.parent / "content" / "phases"

    @cached_property
    def allowed_origins(self) -> list[str]:
        """Combines localhost (dev only), frontend_url, and cors_allowed_origins."""
        origins: list[str] = []

        if self.debug:
            origins.extend(
                [
                    "http://localhost:3000",
                    "http://localhost:4280",
                ]
            )

        if self.frontend_url and self.frontend_url not in origins:
            origins.append(self.frontend_url)

        if self.cors_allowed_origins:
            for origin in self.cors_allowed_origins.split(","):
                origin = origin.strip()
                if origin and origin not in origins:
                    origins.append(origin)

        return origins


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()


def clear_settings_cache() -> None:
    """Clear the settings cache.

    Call this in tests to reset settings between test cases.
    After clearing, the next get_settings() call will create
    a fresh Settings instance with current environment variables.

    Example:
        def test_something(monkeypatch):
            monkeypatch.setenv("ENVIRONMENT", "test")
            clear_settings_cache()
            settings = get_settings()  # Fresh instance
    """
    get_settings.cache_clear()
