"""Application configuration using pydantic-settings."""

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    database_url: str = "sqlite+aiosqlite:///./learn_to_cloud.db"

    postgres_host: str = ""
    postgres_database: str = "learntocloud"
    postgres_user: str = ""

    clerk_secret_key: str = ""
    clerk_webhook_signing_secret: str = ""
    clerk_publishable_key: str = ""

    github_token: str = ""

    google_api_key: str = ""
    gemini_model: str = "gemini-2.0-flash"

    ctf_master_secret: str = "L2C_CTF_MASTER_2024"

    http_timeout: float = 10.0

    frontend_url: str = "http://localhost:4280"

    environment: str = "development"

    reset_db_on_startup: bool = False

    @property
    def use_azure_postgres(self) -> bool:
        """Check if Azure PostgreSQL with managed identity should be used."""
        return bool(self.postgres_host and self.postgres_user)

    @property
    def allowed_origins(self) -> list[str]:
        """Get list of allowed origins for CORS and auth.

        Used by both CORS middleware and Clerk auth validation.
        """
        origins = [
            "http://localhost:3000",
            "http://localhost:4280",
        ]
        if self.frontend_url and self.frontend_url not in origins:
            origins.append(self.frontend_url)
        return origins

@lru_cache
def get_settings() -> Settings:
    """Get cached settings instance."""
    return Settings()
