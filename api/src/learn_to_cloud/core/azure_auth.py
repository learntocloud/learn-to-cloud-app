"""Azure AD token acquisition for PostgreSQL managed identity auth.

Uses ManagedIdentityCredential (native async) for direct IMDS access.
The SDK handles token caching, retries, and refresh internally.
"""

from __future__ import annotations

import asyncio
import os

from azure.identity.aio import ManagedIdentityCredential

AZURE_PG_SCOPE = "https://ossrdbms-aad.database.windows.net/.default"

_azure_credential: ManagedIdentityCredential | None = None
_credential_lock = asyncio.Lock()


async def get_credential() -> ManagedIdentityCredential:
    """Get or create the cached Azure credential.

    Passes AZURE_CLIENT_ID (if set) so ManagedIdentityCredential targets
    the correct user-assigned managed identity on Container Apps.
    """
    global _azure_credential
    async with _credential_lock:
        if _azure_credential is None:
            client_id = os.environ.get("AZURE_CLIENT_ID")
            kwargs = {}
            if client_id:
                kwargs["client_id"] = client_id
            _azure_credential = ManagedIdentityCredential(**kwargs)
        return _azure_credential


async def get_token() -> str:
    """Get Azure AD token for PostgreSQL auth."""
    credential = await get_credential()
    token = await credential.get_token(AZURE_PG_SCOPE)
    return token.token


async def close_credential() -> None:
    """Close the credential's transport session. Call during app shutdown."""
    global _azure_credential
    async with _credential_lock:
        if _azure_credential is not None:
            await _azure_credential.close()
            _azure_credential = None
