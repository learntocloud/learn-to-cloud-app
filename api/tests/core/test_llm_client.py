"""Unit tests for core.llm_client module.

Tests cover:
- LLMClientError has retriable attribute
- get_llm_chat_client raises when not configured
- get_llm_chat_client creates client when configured
- get_llm_chat_client returns cached instance
"""

from unittest.mock import MagicMock, patch

import pytest

from core.llm_client import LLMClientError, get_llm_chat_client


@pytest.fixture(autouse=True)
def _reset_llm_client():
    """Reset the module-level singleton between tests."""
    import core.llm_client as mod

    mod._llm_client = None
    yield
    mod._llm_client = None


# ---------------------------------------------------------------------------
# LLMClientError
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestLLMClientError:
    def test_retriable_defaults_to_false(self):
        err = LLMClientError("fail")
        assert err.retriable is False

    def test_retriable_can_be_set(self):
        err = LLMClientError("fail", retriable=True)
        assert err.retriable is True

    def test_message_preserved(self):
        err = LLMClientError("something broke")
        assert str(err) == "something broke"


# ---------------------------------------------------------------------------
# get_llm_chat_client
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestGetLLMChatClient:
    def test_raises_when_base_url_missing(self):
        mock_settings = MagicMock()
        mock_settings.llm_base_url = ""
        mock_settings.llm_api_key = "key"
        with (
            patch(
                "core.llm_client.get_settings",
                autospec=True,
                return_value=mock_settings,
            ),
            pytest.raises(LLMClientError, match="not configured"),
        ):
            get_llm_chat_client()

    def test_raises_when_api_key_missing(self):
        mock_settings = MagicMock()
        mock_settings.llm_base_url = "https://example.openai.azure.com"
        mock_settings.llm_api_key = ""
        with (
            patch(
                "core.llm_client.get_settings",
                autospec=True,
                return_value=mock_settings,
            ),
            pytest.raises(LLMClientError, match="not configured"),
        ):
            get_llm_chat_client()

    def test_error_is_not_retriable(self):
        mock_settings = MagicMock()
        mock_settings.llm_base_url = ""
        mock_settings.llm_api_key = ""
        with patch(
            "core.llm_client.get_settings",
            autospec=True,
            return_value=mock_settings,
        ):
            with pytest.raises(LLMClientError) as exc_info:
                get_llm_chat_client()
            assert exc_info.value.retriable is False

    def test_creates_client_when_configured(self):
        mock_settings = MagicMock()
        mock_settings.llm_base_url = "https://example.openai.azure.com"
        mock_settings.llm_api_key = "test-key"
        mock_settings.llm_model = "gpt-5-mini"
        mock_settings.llm_api_version = "2024-10-21"
        mock_client_instance = MagicMock()

        with (
            patch(
                "core.llm_client.get_settings",
                autospec=True,
                return_value=mock_settings,
            ),
            patch(
                "agent_framework.azure.AzureOpenAIChatClient",
                autospec=True,
                return_value=mock_client_instance,
            ) as MockClient,
        ):
            result = get_llm_chat_client()

        MockClient.assert_called_once_with(
            endpoint="https://example.openai.azure.com",
            deployment_name="gpt-5-mini",
            api_key="test-key",
            api_version="2024-10-21",
        )
        assert result is mock_client_instance

    def test_returns_cached_instance(self):
        import core.llm_client as mod

        sentinel = MagicMock()
        mod._llm_client = sentinel
        assert get_llm_chat_client() is sentinel

    def test_default_model_when_not_set(self):
        mock_settings = MagicMock()
        mock_settings.llm_base_url = "https://example.openai.azure.com"
        mock_settings.llm_api_key = "test-key"
        mock_settings.llm_model = ""
        mock_settings.llm_api_version = ""

        with (
            patch(
                "core.llm_client.get_settings",
                autospec=True,
                return_value=mock_settings,
            ),
            patch(
                "agent_framework.azure.AzureOpenAIChatClient",
                autospec=True,
            ) as MockClient,
        ):
            get_llm_chat_client()

        call_kwargs = MockClient.call_args[1]
        assert call_kwargs["deployment_name"] == "gpt-5-mini"
        assert call_kwargs["api_version"] == "2024-10-21"
