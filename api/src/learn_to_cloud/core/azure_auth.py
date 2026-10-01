"""Azure AD token acquisition for PostgreSQL managed identity auth.

Uses ManagedIdentityCredential (native async) for direct IMDS access.
The SDK handles token caching, retries, and refresh internally.

Note: azure.identity.aio's default async transport requires the `aiohttp`
package at runtime, even though azure-identity does not declare it as a
dependency. Keep `aiohttp` pinned in pyproject.toml or this raises
`ImportError: aiohttp package is not installed` on first token request.
"""

from __future__ import annotations

import asyncio
import os
from types import TracebackType
from typing import Any

from azure.core.credentials import AccessToken, AccessTokenInfo, TokenRequestOptions
from azure.core.credentials_async import AsyncTokenCredential
from azure.identity.aio import ManagedIdentityCredential

from learn_to_cloud.core.outbound import Dependency, outbound_call

AZURE_PG_SCOPE = "https://ossrdbms-aad.database.windows.net/.default"


class MeasuredCredential:
    """Async Entra credential that records every token request as a dependency call.

    azure-core already traces the token HTTP call, so this adds only the metric.
    Cached tokens are measured too, so the metric's maximum shows slow fetches.
    """

    def __init__(self, inner: AsyncTokenCredential) -> None:
        self._inner = inner

    async def get_token(
        self,
        *scopes: str,
        claims: str | None = None,
        tenant_id: str | None = None,
        enable_cae: bool = False,
        **kwargs: Any,
    ) -> AccessToken:
        async with outbound_call(Dependency.ENTRA, "get_token"):
            return await self._inner.get_token(
                *scopes,
                claims=claims,
                tenant_id=tenant_id,
                enable_cae=enable_cae,
                **kwargs,
            )

    async def get_token_info(
        self, *scopes: str, options: TokenRequestOptions | None = None
    ) -> AccessTokenInfo:
        get_token_info = getattr(self._inner, "get_token_info", None)
        async with outbound_call(Dependency.ENTRA, "get_token"):
            if get_token_info is None:
                token = await self._inner.get_token(*scopes)
                return AccessTokenInfo(token.token, token.expires_on)
            return await get_token_info(*scopes, options=options)

    async def close(self) -> None:
        await self._inner.close()

    async def __aenter__(self) -> MeasuredCredential:
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None = None,
        exc_value: BaseException | None = None,
        traceback: TracebackType | None = None,
    ) -> None:
        await self.close()


_azure_credential: MeasuredCredential | None = None
_credential_lock = asyncio.Lock()


async def get_credential() -> MeasuredCredential:
    """Get or create the cached Azure credential.

    Passes AZURE_CLIENT_ID (if set) so ManagedIdentityCredential targets
    the correct user-assigned managed identity on Container Apps.
    """
    global _azure_credential
    async with _credential_lock:
        if _azure_credential is None:
            client_id = os.environ.get("AZURE_CLIENT_ID")
            _azure_credential = MeasuredCredential(
                ManagedIdentityCredential(client_id=client_id)
            )
        return _azure_credential


async def get_token(scope: str = AZURE_PG_SCOPE) -> str:
    """Get Azure AD token for the requested scope."""
    credential = await get_credential()
    token = await credential.get_token(scope)
    return token.token


async def close_credential() -> None:
    """Close the credential's transport session. Call during app shutdown."""
    global _azure_credential
    async with _credential_lock:
        if _azure_credential is not None:
            await _azure_credential.close()
            _azure_credential = None
