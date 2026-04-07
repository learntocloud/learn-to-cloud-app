"""LLM client infrastructure using Microsoft Agent Framework.

Provides a shared Azure OpenAI chat client (Responses API) for
AI-powered code analysis.  Authenticates via ``DefaultAzureCredential``
(managed identity in prod, Azure CLI / VS Code credential locally).

Configure via environment variables:
  LLM_BASE_URL: Azure OpenAI endpoint (e.g., https://<resource>.openai.azure.com)
  LLM_MODEL: Deployment/model name (e.g., gpt-5-mini)

For business logic using this client, see:
  - services/code_verification_service.py (Phase 3)
  - services/devops_verification_service.py (Phase 5)
"""

import asyncio
import logging

from agent_framework.openai import OpenAIChatClient

from core.config import get_settings

logger = logging.getLogger(__name__)

_llm_client: OpenAIChatClient | None = None
_llm_client_lock = asyncio.Lock()


class LLMClientError(Exception):
    """Raised when LLM client operations fail."""

    def __init__(self, message: str, retriable: bool = False):
        super().__init__(message)
        self.retriable = retriable


async def get_llm_chat_client() -> OpenAIChatClient:
    """Get or create a shared Azure OpenAI chat client (Responses API).

    Uses ``DefaultAzureCredential`` — managed identity in prod,
    Azure CLI (``az login``) or VS Code credential locally.

    Returns:
        OpenAIChatClient configured for Azure OpenAI.

    Raises:
        LLMClientError: If LLM is not configured (missing endpoint).
    """
    global _llm_client

    if _llm_client is not None:
        return _llm_client

    async with _llm_client_lock:
        if _llm_client is not None:
            return _llm_client

        settings = get_settings()

        if not settings.llm_base_url:
            raise LLMClientError(
                "LLM not configured. Set LLM_BASE_URL.",
                retriable=False,
            )

        from core.azure_auth import get_credential

        model = settings.llm_model or "gpt-5-mini"
        credential = await get_credential()

        _llm_client = OpenAIChatClient(
            azure_endpoint=settings.llm_base_url,
            model=model,
            credential=credential,
        )

        logger.info(
            "llm.client.created",
            extra={"model": model, "endpoint": settings.llm_base_url},
        )

        return _llm_client
