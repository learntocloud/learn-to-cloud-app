"""Tests for content-safety handling in the verification grader adapter."""

from __future__ import annotations

import asyncio
import inspect
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import httpx
import openai
import pytest
from agent_framework import Agent
from agent_framework.foundry import FoundryChatClient

from learn_to_cloud.services import verification_grader
from learn_to_cloud.services.verification_grader import (
    ContentFilteredError,
    LLMGradingError,
    _find_content_filter_error,
    classify_llm_error,
    grade_evidence,
)


def test_agent_framework_api_contract() -> None:
    """Pin the Agent Framework surface used by the production grader."""
    agent_parameters = inspect.signature(Agent).parameters
    run_parameters = inspect.signature(Agent.run).parameters
    foundry_parameters = inspect.signature(FoundryChatClient).parameters

    assert {"client", "instructions", "id", "name", "description"} <= set(
        agent_parameters
    )
    assert "messages" in run_parameters
    assert run_parameters["options"].kind is inspect.Parameter.KEYWORD_ONLY
    assert {"project_endpoint", "model", "credential"} <= set(foundry_parameters)


def _content_filter_bad_request() -> openai.BadRequestError:
    request = httpx.Request("POST", "https://example.openai.azure.com/")
    response = httpx.Response(400, request=request)
    return openai.BadRequestError(
        "content filtered",
        response=response,
        body={"code": "content_filter"},
    )


def _library_wrapped_filter_error() -> ValueError:
    """Mimic agent_framework_openai crashing while parsing the filter response.

    The library raises ``ValueError`` from its enum lookup, so the original
    ``BadRequestError`` is only reachable through the ``__context__`` chain.
    """
    try:
        raise _content_filter_bad_request()
    except openai.BadRequestError:
        try:
            raise ValueError("'ContentFiltered' is not a valid ContentFilterCodes")
        except ValueError as value_error:
            return value_error


def test_find_content_filter_error_walks_context_chain() -> None:
    wrapped = _library_wrapped_filter_error()

    found = _find_content_filter_error(wrapped)

    assert found is not None
    assert found.body == {"code": "content_filter"}


def test_find_content_filter_error_ignores_unrelated_errors() -> None:
    assert _find_content_filter_error(ValueError("boom")) is None


class _FakeAgent:
    def __init__(self, exc: BaseException) -> None:
        self._exc = exc

    async def run(self, message: str, *, options: object) -> object:
        raise self._exc


def test_grade_evidence_translates_content_filter(monkeypatch) -> None:
    agent = _FakeAgent(_library_wrapped_filter_error())
    monkeypatch.setattr(
        verification_grader, "get_verification_grader", AsyncMock(return_value=agent)
    )

    with pytest.raises(ContentFilteredError):
        asyncio.run(grade_evidence("grade this"))


def test_grade_evidence_maps_unknown_errors_without_raw_detail(monkeypatch) -> None:
    agent = _FakeAgent(RuntimeError("network down"))
    monkeypatch.setattr(
        verification_grader, "get_verification_grader", AsyncMock(return_value=agent)
    )

    with pytest.raises(LLMGradingError) as caught:
        asyncio.run(grade_evidence("grade this"))
    assert caught.value.error_type == "llm.unknown"
    assert str(caught.value) == "llm.unknown"


def test_grade_evidence_propagates_cancellation(monkeypatch) -> None:
    cancellation = asyncio.CancelledError("Grading was cancelled")
    agent = _FakeAgent(cancellation)
    monkeypatch.setattr(
        verification_grader, "get_verification_grader", AsyncMock(return_value=agent)
    )

    with pytest.raises(asyncio.CancelledError) as caught:
        asyncio.run(grade_evidence("grade this"))

    assert caught.value is cancellation


@pytest.mark.parametrize("status", [502, 503, 504])
def test_grade_evidence_preserves_safe_provider_outage_category(
    monkeypatch, status
) -> None:
    request = httpx.Request("POST", "https://example.com")
    response = httpx.Response(status, request=request)
    error = openai.InternalServerError(
        "private provider response",
        response=response,
        body={"code": "service_unavailable", "message": "private provider response"},
    )
    agent = _FakeAgent(error)
    monkeypatch.setattr(
        verification_grader, "get_verification_grader", AsyncMock(return_value=agent)
    )

    with pytest.raises(LLMGradingError) as caught:
        asyncio.run(grade_evidence("grade this"))

    assert caught.value.error_type == "llm.provider_unavailable"
    assert caught.value.http_status == status
    assert str(caught.value) == "llm.provider_unavailable"


@pytest.mark.parametrize(
    ("exc", "expected"),
    [
        (
            openai.APITimeoutError(
                request=httpx.Request("POST", "https://example.com")
            ),
            "llm.timeout",
        ),
        (
            openai.APIConnectionError(
                request=httpx.Request("POST", "https://example.com")
            ),
            "llm.network",
        ),
    ],
)
def test_classify_llm_error_uses_safe_categories(
    exc: BaseException,
    expected: str,
) -> None:
    assert classify_llm_error(exc).error_type == expected


@pytest.mark.asyncio
async def test_grader_closes_all_transports_and_can_restart(monkeypatch) -> None:
    await verification_grader.close_verification_grader()
    credential = SimpleNamespace(close=AsyncMock())
    client = SimpleNamespace(
        client=SimpleNamespace(close=AsyncMock()),
        project_client=SimpleNamespace(close=AsyncMock()),
    )
    monkeypatch.setenv("FOUNDRY_PROJECT_ENDPOINT", "https://example.com")
    monkeypatch.setenv("FOUNDRY_MODEL_DEPLOYMENT_NAME", "grader")
    monkeypatch.setattr(
        verification_grader, "_credential", Mock(return_value=credential)
    )
    factory = Mock(return_value=client)
    monkeypatch.setattr(verification_grader, "FoundryChatClient", factory)
    agent_factory = Mock(side_effect=[object(), object()])
    monkeypatch.setattr(verification_grader, "Agent", agent_factory)

    first = await verification_grader.get_verification_grader()
    assert await verification_grader.get_verification_grader() is first
    factory.assert_called_once()
    await verification_grader.close_verification_grader()
    client.client.close.assert_awaited_once()
    client.project_client.close.assert_awaited_once()
    credential.close.assert_awaited_once()
    await verification_grader.close_verification_grader()
    credential.close.assert_awaited_once()
    assert await verification_grader.get_verification_grader() is not first
    await verification_grader.close_verification_grader()
    assert credential.close.await_count == 2


@pytest.mark.asyncio
async def test_grader_initialization_failure_closes_credential(monkeypatch) -> None:
    await verification_grader.close_verification_grader()
    credential = SimpleNamespace(close=AsyncMock())
    monkeypatch.setenv("FOUNDRY_PROJECT_ENDPOINT", "https://example.com")
    monkeypatch.setenv("FOUNDRY_MODEL_DEPLOYMENT_NAME", "grader")
    monkeypatch.setattr(
        verification_grader, "_credential", Mock(return_value=credential)
    )
    monkeypatch.setattr(
        verification_grader, "FoundryChatClient", Mock(side_effect=ValueError())
    )

    with pytest.raises(ValueError):
        await verification_grader.get_verification_grader()

    credential.close.assert_awaited_once()
    assert verification_grader._grader is None


@pytest.mark.parametrize("development", [False, True])
def test_credential_uses_api_environment(monkeypatch, development) -> None:
    monkeypatch.setattr(
        verification_grader,
        "get_web_settings",
        lambda: SimpleNamespace(is_development=development),
    )
    monkeypatch.setenv("AZURE_CLIENT_ID", "api-identity")
    default = Mock()
    managed = Mock()
    monkeypatch.setattr(verification_grader, "DefaultAzureCredential", default)
    monkeypatch.setattr(verification_grader, "ManagedIdentityCredential", managed)

    verification_grader._credential()

    if development:
        default.assert_called_once_with()
        managed.assert_not_called()
    else:
        managed.assert_called_once_with(client_id="api-identity")
        default.assert_not_called()


@pytest.mark.asyncio
async def test_foundry_supports_async_credentials_and_transport_cleanup() -> None:
    from azure.identity.aio import ManagedIdentityCredential

    credential = ManagedIdentityCredential()
    client = FoundryChatClient(
        project_endpoint="https://example.services.ai.azure.com/api/projects/test",
        model="grader",
        credential=credential,
    )
    await client.client.close()
    await client.project_client.close()
    await credential.close()
