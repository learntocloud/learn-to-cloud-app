"""Synchronous database URL builder shared by the alembic env and helper scripts.

Lives in the ``learn_to_cloud`` package rather than the alembic directory so
non-alembic callers (notably ``scripts/run_migrations.py`` post-upgrade
verification) can import the URL helper without triggering ``env.py``'s
module-level ``run()`` call, which would execute migrations as a side effect.
"""

from __future__ import annotations

import os
import time

from azure.identity import DefaultAzureCredential
from learn_to_cloud_shared.core.azure_auth import AZURE_PG_SCOPE
from learn_to_cloud_shared.core.config import get_settings


def _get_azure_token_with_retry() -> str:
    """Get an Entra ID access token for PostgreSQL with retry.

    Uses the sync credential because alembic runs outside an asyncio loop.
    On Container Apps cold starts the managed identity sidecar can take
    up to ~30s to come up, so we retry with exponential backoff.
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
            token = credential.get_token(AZURE_PG_SCOPE)
            return token.token
        except Exception as e:
            last_error = e
            if attempt < max_attempts - 1:
                time.sleep(initial_wait * (2**attempt))

    raise RuntimeError(
        f"Failed to acquire Azure AD token after {max_attempts} attempts"
    ) from last_error


def get_sync_database_url() -> str:
    """Return a psycopg2 URL suitable for alembic.

    Uses psycopg2 (synchronous) instead of asyncpg to avoid event loop
    conflicts when running in background threads or one-off scripts.
    """
    settings = get_settings()
    if settings.use_azure_postgres:
        token = _get_azure_token_with_retry()
        return (
            f"postgresql+psycopg2://{settings.postgres_user}:{token}"
            f"@{settings.postgres_host}:{settings.postgres_port}/{settings.postgres_database}"
            f"?sslmode=require"
        )

    url = settings.database_url
    if "+asyncpg" in url:
        url = url.replace("+asyncpg", "+psycopg2")
    return url
