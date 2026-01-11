"""Application configuration using pydantic-settings."""

import os
from pydantic_settings import BaseSettings
from functools import lru_cache


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""
    
    # Database
    database_url: str = "sqlite+aiosqlite:///./learn_to_cloud.db"
    
    # Clerk
    clerk_secret_key: str = ""
    clerk_webhook_signing_secret: str = ""
    clerk_publishable_key: str = ""
    
    # Frontend URL for CORS
    frontend_url: str = "http://localhost:4280"
    
    # Environment
    environment: str = "development"
    
    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


@lru_cache
def get_settings() -> Settings:
    """Get cached settings instance."""
    return Settings()
