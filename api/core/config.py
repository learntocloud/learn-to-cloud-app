"""Application configuration using pydantic-settings."""

from functools import cached_property, lru_cache

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # SQLite is for local development only - will fail-fast in non-dev environments
    # For production, set postgres_host + postgres_user (Azure MI)
    # or override database_url with a PostgreSQL connection string
    database_url: str = "sqlite+aiosqlite:///./learn_to_cloud.db"

    # Azure PostgreSQL with Managed Identity - takes precedence over database_url
    # When postgres_host is set, database_url is derived automatically
    postgres_host: str = ""
    postgres_database: str = "learntocloud"
    postgres_user: str = ""

    # Comma-separated list of allowed CORS origins (in addition to localhost defaults)
    # Example: "https://app.example.com,https://staging.example.com"
    cors_allowed_origins: str = ""

    clerk_secret_key: str = ""
    clerk_webhook_signing_secret: str = ""
    clerk_publishable_key: str = ""

    github_token: str = ""

    google_api_key: str = ""
    gemini_model: str = "gemini-2.0-flash"

    # CTF secret - must be set via env var in non-development environments
    ctf_master_secret: str = ""

    http_timeout: float = 10.0

    # Use "redis://host:port" in production for distributed rate limiting
    # memory:// only works for single-instance deployments
    ratelimit_storage_uri: str = "memory://"

    frontend_url: str = "http://localhost:4280"

    # Database pool settings (PostgreSQL only)
    # Keep pool sizes small for horizontal scaling (multiple workers/replicas)
    # Total connections per worker = pool_size + max_overflow
    db_pool_size: int = 5
    db_pool_max_overflow: int = 5
    db_pool_timeout: int = 30
    db_pool_recycle: int = 300
    db_statement_timeout_ms: int = 10000  # 10 seconds - prevents pool starvation
    db_echo: bool = False  # Set True to log all SQL queries (very verbose)

    environment: str = "development"

    @model_validator(mode="after")
    def validate_production_config(self) -> "Settings":
        """Validate configuration for non-development environments."""
        if self.environment != "development":
            # Fail-fast: SQLite is not supported in production
            if "sqlite" in self.database_url and not self.use_azure_postgres:
                raise ValueError(
                    "SQLite is not supported in production. "
                    "Set POSTGRES_HOST + POSTGRES_USER for Azure, "
                    "or provide a PostgreSQL DATABASE_URL."
                )
            # Require CTF secret in production
            if not self.ctf_master_secret:
                raise ValueError(
                    "CTF_MASTER_SECRET must be set in non-development environments."
                )
        return self

    @property
    def use_azure_postgres(self) -> bool:
        """Check if Azure PostgreSQL with managed identity should be used.

        When True, database_url is ignored and connection is built from
        the postgres_* fields instead.
        """
        return bool(self.postgres_host and self.postgres_user)

    @cached_property
    def allowed_origins(self) -> list[str]:
        """Get list of allowed origins for CORS and auth.

        Combines:
        - Default localhost origins (development only)
        - frontend_url (convenience for single frontend)
        - cors_allowed_origins (comma-separated, for multiple environments)

        Thread-safe via @cached_property (computed once per instance).
        """
        origins: list[str] = []

        # Only include localhost origins in development
        if self.environment == "development":
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


@lru_cache
def get_settings() -> Settings:
    """Get cached settings instance."""
    return Settings()
