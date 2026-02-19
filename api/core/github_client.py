"""Shared HTTP client for GitHub API requests.

Provides a connection-pooled ``httpx.AsyncClient`` used by all services
that talk to the GitHub API.  Previously this lived as a private function
in ``github_hands_on_verification_service`` but is imported by 4+ services.
"""

from __future__ import annotations

import asyncio

import httpx

from core.config import get_settings

_github_http_client: httpx.AsyncClient | None = None
_github_client_lock = asyncio.Lock()


async def get_github_client() -> httpx.AsyncClient:
    """Get or create a shared HTTP client for GitHub API requests.

    Uses connection pooling to reduce overhead from per-request client creation.
    Thread-safe via asyncio.Lock to prevent race conditions.
    """
    global _github_http_client

    if _github_http_client is not None and not _github_http_client.is_closed:
        return _github_http_client

    async with _github_client_lock:
        if _github_http_client is not None and not _github_http_client.is_closed:
            return _github_http_client

        settings = get_settings()
        _github_http_client = httpx.AsyncClient(
            timeout=settings.http_timeout,
            follow_redirects=True,
            limits=httpx.Limits(max_connections=20, max_keepalive_connections=10),
        )
        return _github_http_client


async def close_github_client() -> None:
    """Close the shared GitHub HTTP client (called on application shutdown)."""
    global _github_http_client
    if _github_http_client is not None and not _github_http_client.is_closed:
        await _github_http_client.aclose()
    _github_http_client = None
