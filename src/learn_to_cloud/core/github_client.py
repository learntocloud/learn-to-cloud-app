"""Shared HTTP client for GitHub API requests.

Provides a connection-pooled ``httpx2.AsyncClient`` used by all services
that talk to the GitHub API.
"""

from __future__ import annotations

import httpx2

from learn_to_cloud.core.config import get_worker_settings
from learn_to_cloud.core.http_client import PooledClient


def _build_github_client() -> httpx2.AsyncClient:
    settings = get_worker_settings()
    return httpx2.AsyncClient(
        timeout=settings.http.external_api_timeout,
        follow_redirects=True,
        limits=httpx2.Limits(max_connections=20, max_keepalive_connections=10),
    )


_pool = PooledClient(_build_github_client)


async def get_github_client() -> httpx2.AsyncClient:
    """Get or create a shared HTTP client for GitHub API requests."""
    return await _pool.get()


async def close_github_client() -> None:
    """Close the shared GitHub HTTP client (called on application shutdown)."""
    await _pool.close()
