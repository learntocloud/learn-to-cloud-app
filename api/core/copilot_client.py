"""GitHub Copilot CLI client infrastructure.

This module provides connection management for the GitHub Copilot SDK,
which communicates with the Copilot CLI via JSON-RPC.

Supports two modes:
  1. Stdio mode (local dev): SDK manages CLI process lifecycle via stdin/stdout
  2. HTTP mode (production): CLI runs as sidecar, SDK connects via HTTP

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

    The client connects to the Copilot CLI server in one of two modes:
      - Stdio mode: SDK starts and manages CLI process (copilot_cli_path set)
      - HTTP mode: Connect to external CLI sidecar (copilot_cli_url set)

    Raises:
        CopilotClientError: If neither CLI path nor URL is configured,
            or if connection fails.
    """
    global _copilot_client

    if _copilot_client is not None:
        return _copilot_client

    async with _copilot_client_lock:
        # Double-check after acquiring lock
        if _copilot_client is not None:
            return _copilot_client

        settings = get_settings()

        # Validate configuration
        if not settings.copilot_cli_path and not settings.copilot_cli_url:
            raise CopilotClientError(
                "Copilot CLI not configured. "
                "Set COPILOT_CLI_PATH (local) or COPILOT_CLI_URL (sidecar).",
                retriable=False,
            )

        try:
            from copilot import CopilotClient
            from copilot.types import CopilotClientOptions

            # Stdio mode: SDK manages CLI process
            if settings.copilot_cli_path:
                options = CopilotClientOptions(
                    cli_path=settings.copilot_cli_path,
                    use_stdio=True,
                    auto_start=True,  # SDK starts CLI process
                )
                log_detail = {"mode": "stdio", "cli_path": settings.copilot_cli_path}
            # HTTP mode: Connect to external sidecar
            else:
                options = CopilotClientOptions(
                    cli_url=settings.copilot_cli_url,
                    auto_start=False,  # CLI runs externally
                )
                log_detail = {"mode": "http", "cli_url": settings.copilot_cli_url}

            _copilot_client = CopilotClient(options)
            await _copilot_client.start()

            logger.info("copilot.client.connected", **log_detail)

            return _copilot_client

        except ImportError as e:
            raise CopilotClientError(
                "github-copilot-sdk package not installed. "
                "Install with: pip install github-copilot-sdk",
                retriable=False,
            ) from e
        except Exception as e:
            log_info = (
                {"cli_path": settings.copilot_cli_path}
                if settings.copilot_cli_path
                else {"cli_url": settings.copilot_cli_url}
            )
            logger.error(
                "copilot.client.connection_failed",
                **log_info,
                error=str(e),
            )
            raise CopilotClientError(
                f"Failed to connect to Copilot CLI: {e}",
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
