"""Shared HTTP client for GitHub API requests.

Provides a connection-pooled ``httpx.AsyncClient`` used by all services
that talk to the GitHub API.
"""

from __future__ import annotations

import httpx

from learn_to_cloud_shared.core.config import get_settings
from learn_to_cloud_shared.core.http_client import PooledClient


def _build_github_client() -> httpx.AsyncClient:
    settings = get_settings()
    return httpx.AsyncClient(
        timeout=settings.external_api_timeout,
        follow_redirects=True,
        limits=httpx.Limits(max_connections=20, max_keepalive_connections=10),
    )


_pool = PooledClient(_build_github_client)


async def get_github_client() -> httpx.AsyncClient:
    """Get or create a shared HTTP client for GitHub API requests."""
    return await _pool.get()


async def close_github_client() -> None:
    """Close the shared GitHub HTTP client (called on application shutdown)."""
    await _pool.close()
