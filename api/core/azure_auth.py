"""Azure AD token acquisition for PostgreSQL managed identity auth.

Handles credential caching, token acquisition with retry/timeout,
and credential reset on transient failures.
"""

from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING

from tenacity import (
    before_sleep_log,
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

if TYPE_CHECKING:
    from azure.identity import DefaultAzureCredential

AZURE_TOKEN_TIMEOUT = 30

_AZURE_RETRY_ATTEMPTS = 3
_AZURE_RETRY_MIN_WAIT = 1  # seconds
_AZURE_RETRY_MAX_WAIT = 10  # seconds

AZURE_PG_SCOPE = "https://ossrdbms-aad.database.windows.net/.default"

_azure_credential: DefaultAzureCredential | None = None
_credential_lock = asyncio.Lock()


async def get_credential() -> DefaultAzureCredential:
    """Get or create the cached Azure credential (thread-safe via asyncio.Lock).

    Passes AZURE_CLIENT_ID (if set) so DefaultAzureCredential targets
    the correct user-assigned managed identity on Container Apps.
    """
    global _azure_credential
    async with _credential_lock:
        if _azure_credential is None:
            import os

            from azure.identity import DefaultAzureCredential

            client_id = os.environ.get("AZURE_CLIENT_ID")
            kwargs = {}
            if client_id:
                kwargs["managed_identity_client_id"] = client_id
            _azure_credential = DefaultAzureCredential(**kwargs)
        return _azure_credential


async def reset_credential() -> None:
    """Reset the cached credential (e.g., after timeout). Thread-safe."""
    global _azure_credential
    async with _credential_lock:
        _azure_credential = None


def _get_token_sync(credential: DefaultAzureCredential) -> str:
    """Get an Azure AD token for PostgreSQL authentication (sync, may block).

    Args:
        credential: A pre-fetched Azure credential instance.

    Note: Retry logic is handled by the async wrapper to properly coordinate
    with asyncio timeout and credential reset.
    """
    token = credential.get_token(AZURE_PG_SCOPE)
    return token.token


# tenacity's before_sleep_log requires a stdlib Logger
_stdlib_logger = logging.getLogger(__name__)


@retry(
    stop=stop_after_attempt(_AZURE_RETRY_ATTEMPTS),
    wait=wait_exponential(
        multiplier=1, min=_AZURE_RETRY_MIN_WAIT, max=_AZURE_RETRY_MAX_WAIT
    ),
    # Retry on transient failures only - not programming errors
    # TimeoutError: token acquisition timeout
    # OSError: network issues (includes ConnectionError, socket errors)
    retry=retry_if_exception_type((TimeoutError, OSError)),
    before_sleep=before_sleep_log(_stdlib_logger, logging.WARNING),
    reraise=True,
)
async def get_token() -> str:
    """Get Azure AD token for PostgreSQL auth without blocking event loop.

    Includes retry logic with exponential backoff for transient failures
    (IMDS timeouts, network blips) and a per-attempt timeout.
    """
    credential = await get_credential()
    try:
        async with asyncio.timeout(AZURE_TOKEN_TIMEOUT):
            return await asyncio.to_thread(_get_token_sync, credential)
    except TimeoutError:
        # Reset credential on timeout in case it's in a bad state
        await reset_credential()
        raise
