"""Shared HTTP client for GitHub API requests.

Provides a connection-pooled ``httpx.AsyncClient`` used by all services
that talk to the GitHub API.
"""

from __future__ import annotations

import httpx

from learn_to_cloud_shared.core.config import get_worker_settings
from learn_to_cloud_shared.core.http_client import PooledClient, build_http_client
from learn_to_cloud_shared.core.outbound import Dependency


def _build_github_client() -> httpx.AsyncClient:
    settings = get_worker_settings()
    return build_http_client(
        Dependency.GITHUB,
        timeout=settings.http.external_api_timeout,
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
