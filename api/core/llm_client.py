"""LLM client infrastructure for AI-powered code analysis.

This module provides connection management for the LLM SDK (github-copilot-sdk),
which communicates with the CLI server via JSON-RPC.

Supports two modes:
  1. Stdio mode (local dev): SDK manages CLI process lifecycle via stdin/stdout
  2. HTTP mode (production): CLI runs as sidecar, SDK connects via HTTP

Authentication uses BYOK (Bring Your Own Key) exclusively:
  Configure LLM_BASE_URL, LLM_API_KEY, and LLM_MODEL env vars to point
  at your model deployment (Azure AI Foundry, OpenAI, Anthropic).

For business logic using this client, see services/code_verification_service.py
"""

import asyncio
from typing import TYPE_CHECKING

from core import get_logger
from core.config import get_settings

if TYPE_CHECKING:
    from copilot import CopilotClient
    from copilot.types import SessionConfig

logger = get_logger(__name__)

# Shared LLM client instance (lazy initialization)
_llm_client: "CopilotClient | None" = None
_llm_client_lock = asyncio.Lock()


class LLMClientError(Exception):
    """Raised when LLM client operations fail."""

    def __init__(self, message: str, retriable: bool = False):
        super().__init__(message)
        self.retriable = retriable


async def get_llm_client() -> "CopilotClient":
    """Get or create a shared LLM client instance.

    The client connects to the CLI server in one of two modes:
      - Stdio mode: SDK starts and manages CLI process (llm_cli_path set)
      - HTTP mode: Connect to external CLI sidecar (llm_cli_url set)

    Raises:
        LLMClientError: If neither CLI path nor URL is configured,
            or if connection fails.
    """
    global _llm_client

    if _llm_client is not None:
        return _llm_client

    async with _llm_client_lock:
        # Double-check after acquiring lock
        if _llm_client is not None:
            return _llm_client

        settings = get_settings()

        # Validate configuration
        if not settings.llm_cli_path and not settings.llm_cli_url:
            raise LLMClientError(
                "LLM CLI not configured. "
                "Set LLM_CLI_PATH (local) or LLM_CLI_URL (sidecar).",
                retriable=False,
            )

        try:
            from copilot import CopilotClient
            from copilot.types import CopilotClientOptions

            # Stdio mode: SDK manages CLI process
            if settings.llm_cli_path:
                options = CopilotClientOptions(
                    cli_path=settings.llm_cli_path,
                    use_stdio=True,
                    auto_start=True,  # SDK starts CLI process
                )
                log_detail = {"mode": "stdio", "cli_path": settings.llm_cli_path}
            # HTTP mode: Connect to external sidecar
            else:
                options = CopilotClientOptions(
                    cli_url=settings.llm_cli_url,
                    auto_start=False,  # CLI runs externally
                )
                log_detail = {"mode": "http", "cli_url": settings.llm_cli_url}

            _llm_client = CopilotClient(options)
            await _llm_client.start()

            logger.info("llm.client.connected", **log_detail)

            return _llm_client

        except ImportError as e:
            raise LLMClientError(
                "github-copilot-sdk package not installed. "
                "Install with: pip install github-copilot-sdk",
                retriable=False,
            ) from e
        except Exception as e:
            log_info = (
                {"cli_path": settings.llm_cli_path}
                if settings.llm_cli_path
                else {"cli_url": settings.llm_cli_url}
            )
            logger.error(
                "llm.client.connection_failed",
                **log_info,
                error=str(e),
            )
            raise LLMClientError(
                f"Failed to connect to LLM CLI: {e}",
                retriable=True,
            ) from e


async def close_llm_client() -> None:
    """Close the shared LLM client (called on application shutdown)."""
    global _llm_client

    if _llm_client is not None:
        try:
            await _llm_client.stop()
            logger.info("llm.client.closed")
        except Exception as e:
            logger.warning("llm.client.close_error", error=str(e))
        finally:
            _llm_client = None


def build_session_config(*, tools: list[object] | None = None) -> "SessionConfig":
    """Build a SessionConfig dict with the BYOK provider.

    Requires LLM_BASE_URL, LLM_API_KEY, and LLM_MODEL to be configured.

    Args:
        tools: Optional list of Tool objects for the session.

    Raises:
        LLMClientError: If BYOK provider is not configured.

    Returns:
        SessionConfig dict for ``client.create_session(config)``.
    """
    from copilot.types import SessionConfig

    settings = get_settings()
    provider = settings.byok_provider

    if not provider:
        raise LLMClientError(
            "BYOK provider not configured. "
            "Set LLM_BASE_URL, LLM_API_KEY, and "
            "LLM_MODEL environment variables.",
            retriable=False,
        )

    model = settings.llm_model or "gpt-5-mini"
    config = SessionConfig(
        model=model,  # type: ignore[arg-type] - model value comes from config
        provider=provider,
    )
    logger.debug(
        "llm.session.configured",
        model=model,
        provider_type=settings.llm_provider_type,
    )

    if tools:
        config["tools"] = tools  # type: ignore[assignment] - list[object] vs list[Tool]

    return config
