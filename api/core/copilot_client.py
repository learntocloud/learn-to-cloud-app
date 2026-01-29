"""GitHub Copilot CLI client infrastructure.

This module provides connection management for the GitHub Copilot SDK,
which communicates with the Copilot CLI server via JSON-RPC.

The CLI runs as a sidecar container in production, exposing a server
that handles AI-powered code analysis requests.

For business logic using this client, see services/copilot_verification_service.py
"""

import asyncio
from typing import TYPE_CHECKING

from core import get_logger
from core.config import get_settings

if TYPE_CHECKING:
    from copilot import CopilotClient

logger = get_logger(__name__)

# Shared Copilot client instance (lazy initialization)
_copilot_client: "CopilotClient | None" = None
_copilot_client_lock = asyncio.Lock()


class CopilotClientError(Exception):
    """Raised when Copilot client operations fail."""

    def __init__(self, message: str, retriable: bool = False):
        super().__init__(message)
        self.retriable = retriable


async def get_copilot_client() -> "CopilotClient":
    """Get or create a shared Copilot client instance.

    The client connects to the Copilot CLI server specified by copilot_cli_url.
    Uses lazy initialization with lock to prevent race conditions.

    Raises:
        CopilotClientError: If CLI URL is not configured or connection fails.
    """
    global _copilot_client

    if _copilot_client is not None:
        return _copilot_client

    async with _copilot_client_lock:
        # Double-check after acquiring lock
        if _copilot_client is not None:
            return _copilot_client

        settings = get_settings()

        if not settings.copilot_cli_url:
            raise CopilotClientError(
                "Copilot CLI URL not configured. "
                "Set COPILOT_CLI_URL environment variable.",
                retriable=False,
            )

        try:
            from copilot import CopilotClient
            from copilot.types import CopilotClientOptions

            options = CopilotClientOptions(
                cli_url=settings.copilot_cli_url,
                auto_start=False,  # CLI runs as external sidecar
            )
            _copilot_client = CopilotClient(options)
            await _copilot_client.start()

            logger.info(
                "copilot.client.connected",
                cli_url=settings.copilot_cli_url,
            )

            return _copilot_client

        except ImportError as e:
            raise CopilotClientError(
                "github-copilot-sdk package not installed. "
                "Install with: pip install github-copilot-sdk",
                retriable=False,
            ) from e
        except Exception as e:
            logger.error(
                "copilot.client.connection_failed",
                cli_url=settings.copilot_cli_url,
                error=str(e),
            )
            raise CopilotClientError(
                f"Failed to connect to Copilot CLI server: {e}",
                retriable=True,
            ) from e


async def close_copilot_client() -> None:
    """Close the shared Copilot client (called on application shutdown)."""
    global _copilot_client

    if _copilot_client is not None:
        try:
            await _copilot_client.stop()
            logger.info("copilot.client.closed")
        except Exception as e:
            logger.warning("copilot.client.close_error", error=str(e))
        finally:
            _copilot_client = None
