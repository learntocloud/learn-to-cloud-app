"""LLM client infrastructure using Microsoft Agent Framework.

Provides a shared Azure OpenAI chat client for AI-powered code analysis.
Uses the Agent Framework's AzureOpenAIChatClient with API key auth.

Configure via environment variables:
  LLM_BASE_URL: Azure OpenAI endpoint (e.g., https://<resource>.openai.azure.com)
  LLM_API_KEY: API key for the deployment
  LLM_MODEL: Deployment/model name (e.g., gpt-5-mini)

For business logic using this client, see:
  - services/code_verification_service.py (Phase 3)
  - services/devops_verification_service.py (Phase 5)
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from core.config import get_settings

if TYPE_CHECKING:
    from agent_framework.azure import AzureOpenAIChatClient

logger = logging.getLogger(__name__)

# Shared client instance (lazy initialization)
_llm_client: AzureOpenAIChatClient | None = None


class LLMClientError(Exception):
    """Raised when LLM client operations fail."""

    def __init__(self, message: str, retriable: bool = False):
        super().__init__(message)
        self.retriable = retriable


def get_llm_chat_client() -> AzureOpenAIChatClient:
    """Get or create a shared Azure OpenAI chat client.

    Returns:
        AzureOpenAIChatClient configured with settings from environment.

    Raises:
        LLMClientError: If LLM is not configured (missing env vars).
    """
    global _llm_client

    if _llm_client is not None:
        return _llm_client

    settings = get_settings()

    if not settings.llm_base_url or not settings.llm_api_key:
        raise LLMClientError(
            "LLM not configured. Set LLM_BASE_URL and LLM_API_KEY.",
            retriable=False,
        )

    from agent_framework.azure import AzureOpenAIChatClient

    model = settings.llm_model or "gpt-5-mini"

    _llm_client = AzureOpenAIChatClient(
        endpoint=settings.llm_base_url,
        deployment_name=model,
        api_key=settings.llm_api_key,
        api_version=settings.llm_api_version or "2024-10-21",
    )

    logger.info(
        "llm.client.created",
        extra={"model": model, "endpoint": settings.llm_base_url},
    )

    return _llm_client
