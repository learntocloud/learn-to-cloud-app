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

    # PostgreSQL connection - set via DATABASE_URL env var
    # For Azure: set postgres_host + postgres_user (Managed Identity)
    # For local: use "postgresql+asyncpg://postgres:postgres@localhost:5432/learn_to_cloud"
    database_url: str = ""

    # Azure PostgreSQL with Managed Identity - takes precedence over database_url
    # When postgres_host is set, database_url is derived automatically
    postgres_host: str = ""
    postgres_port: int = 5432
    postgres_database: str = "learntocloud"
    postgres_user: str = ""

    # Comma-separated list of allowed CORS origins (in addition to localhost defaults)
    # Example: "https://app.example.com,https://staging.example.com"
    cors_allowed_origins: str = ""

    # GitHub OAuth (Authlib)
    github_client_id: str = ""
    github_client_secret: str = ""

    # Session cookie signing key
    # Generate with: python -c "import secrets; print(secrets.token_hex(32))"
    session_secret_key: str = "dev-secret-key-change-in-production"

    github_token: str = ""

    google_api_key: str = ""
    gemini_model: str = "gemini-2.0-flash"

    # CTF secret - must be set via env var in non-development environments
    labs_verification_secret: str = ""

    http_timeout: float = 10.0

    # Copilot CLI configuration for AI-powered code verification
    # Two modes:
    #   1. Stdio mode (local dev): Set COPILOT_CLI_PATH to CLI binary
    #   2. HTTP mode (production): Set COPILOT_CLI_URL to sidecar URL
    copilot_cli_path: str = ""  # Path to CLI binary for stdio mode
    copilot_cli_url: str = ""  # URL for HTTP mode (e.g., "http://127.0.0.1:8080")
    copilot_cli_timeout: int = 120  # Seconds to wait for code analysis completion
    code_analysis_cooldown_seconds: int = 3600  # 1 hr between code analysis
    submission_cooldown_seconds: int = 3600  # 1 hr between verification attempts

    # Use "redis://host:port" in production for distributed rate limiting
    # memory:// only works for single-instance deployments
    ratelimit_storage_uri: str = "memory://"

    frontend_url: str = "http://localhost:4280"

    # Content directory for course phases JSON files
    # Defaults to frontend/public/content/phases for local dev
    content_dir: str = ""

    # Database pool settings (PostgreSQL only)
    # Keep pool sizes small for horizontal scaling (multiple workers/replicas)
    # Total connections per worker = pool_size + max_overflow
    db_pool_size: int = 5
    db_pool_max_overflow: int = 5
    db_pool_timeout: int = 30
    db_pool_recycle: int = 300
    db_statement_timeout_ms: int = 10000  # 10 seconds - prevents pool starvation
    db_echo: bool = False  # Set True to log all SQL queries (very verbose)

    # Feature flags — production defaults (fail-safe)
    # Set DEBUG=true in .env for local development
    debug: bool = False  # Enables docs, CORS localhost, relaxes validation
    require_https: bool = True  # Session cookies require HTTPS
    enable_docs: bool = False  # Swagger UI at /docs

    @model_validator(mode="after")
    def validate_config(self) -> Self:
        # Require PostgreSQL configuration
        if not self.database_url and not self.use_azure_postgres:
            raise ValueError(
                "Database configuration required. "
                "Set DATABASE_URL for direct connection, "
                "or POSTGRES_HOST + POSTGRES_USER for Azure Managed Identity."
            )

        # In production (debug=False), require auth and security config
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
            if not self.labs_verification_secret:
                raise ValueError(
                    "LABS_VERIFICATION_SECRET must be set. "
                    "Set DEBUG=true to skip this check in development."
                )
        return self

    @property
    def use_azure_postgres(self) -> bool:
        """When True, connection built from postgres_* fields instead."""
        return bool(self.postgres_host and self.postgres_user)

    @cached_property
    def content_dir_path(self) -> Path:
        """Defaults to frontend/public/content/phases if CONTENT_DIR not set."""
        if self.content_dir:
            return Path(self.content_dir)
        # Default: assume running from api/ directory
        return (
            Path(__file__).parent.parent.parent
            / "frontend"
            / "public"
            / "content"
            / "phases"
        )

    @cached_property
    def allowed_origins(self) -> list[str]:
        """Combines localhost (dev only), frontend_url, and cors_allowed_origins."""
        origins: list[str] = []

        # Only include localhost origins in debug mode
        if self.debug:
            origins.extend(
                [
                    "http://localhost:3000",
                    "http://localhost:4280",
                ]
            )

        # Add frontend_url if not already present
        if self.frontend_url and self.frontend_url not in origins:
            origins.append(self.frontend_url)

        # Add any additional origins from cors_allowed_origins (comma-separated)
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
