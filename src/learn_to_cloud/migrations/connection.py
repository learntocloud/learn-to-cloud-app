"""Database connection for the migration job."""

from __future__ import annotations

import os
import time

from azure.identity import DefaultAzureCredential
from sqlalchemy import URL, make_url
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine
from sqlalchemy.pool import NullPool

from learn_to_cloud.core.azure_auth import AZURE_PG_SCOPE
from learn_to_cloud.core.config import get_migration_settings


def _get_azure_token_with_retry() -> str:
    """Return an Entra ID token for PostgreSQL with retry.

    Managed-identity sidecars can take up to ~30s to come up on Container
    Apps cold starts, so we retry a handful of times with exponential
    backoff before giving up.
    """
    max_attempts = 6
    initial_wait = 2

    client_id = os.environ.get("AZURE_CLIENT_ID")
    cred_kwargs: dict[str, str] = {}
    if client_id:
        cred_kwargs["managed_identity_client_id"] = client_id

    last_error: Exception | None = None
    for attempt in range(max_attempts):
        try:
            credential = DefaultAzureCredential(**cred_kwargs)
            return credential.get_token(AZURE_PG_SCOPE).token
        except Exception as e:
            last_error = e
            if attempt < max_attempts - 1:
                time.sleep(initial_wait * (2**attempt))

    raise RuntimeError(
        f"Failed to acquire Azure AD token after {max_attempts} attempts"
    ) from last_error


def database_url(*, with_token: bool) -> URL:
    """Return an asyncpg URL; offline mode only needs the dialect."""
    settings = get_migration_settings().database
    if settings.use_azure_postgres:
        return URL.create(
            "postgresql+asyncpg",
            username=settings.user,
            password=_get_azure_token_with_retry() if with_token else None,
            host=settings.host,
            port=settings.port,
            database=settings.name,
            query={"ssl": "require"},
        )
    return make_url(settings.url)


def create_migration_engine() -> AsyncEngine:
    """Create a single-use engine for the migration job's database work."""
    return create_async_engine(database_url(with_token=True), poolclass=NullPool)
