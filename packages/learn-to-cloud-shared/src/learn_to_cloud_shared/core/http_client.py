"""Shared lazy-singleton factory for pooled ``httpx.AsyncClient`` instances.

Multiple services (GitHub API, deployed-API verification) need a long-lived,
connection-pooled async client.  Rather than each module rolling its own
double-checked-locking singleton, they share this helper.
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable

import httpx


class PooledClient:
    """Lazy, async-safe singleton wrapper around a pooled ``httpx.AsyncClient``.

    The first call to :meth:`get` builds the client by invoking *factory*;
    subsequent calls return the same instance until :meth:`close` is called
    (or the client is closed externally).
    """

    def __init__(self, factory: Callable[[], httpx.AsyncClient]):
        self._factory = factory
        self._client: httpx.AsyncClient | None = None
        self._lock = asyncio.Lock()

    async def get(self) -> httpx.AsyncClient:
        if self._client is not None and not self._client.is_closed:
            return self._client

        async with self._lock:
            if self._client is not None and not self._client.is_closed:
                return self._client
            self._client = self._factory()
            return self._client

    async def close(self) -> None:
        if self._client is not None and not self._client.is_closed:
            await self._client.aclose()
        self._client = None
