"""Tests for content-safety handling in the verification grader adapter."""

from __future__ import annotations

import asyncio
import inspect

import httpx
import openai
import pytest
from agent_framework import Agent
from agent_framework.foundry import FoundryChatClient

import verification_agents
from verification_agents import (
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
    monkeypatch.setattr(verification_agents, "get_verification_grader", lambda: agent)

    with pytest.raises(ContentFilteredError):
        asyncio.run(grade_evidence("grade this"))


def test_grade_evidence_maps_unknown_errors_without_raw_detail(monkeypatch) -> None:
    agent = _FakeAgent(RuntimeError("network down"))
    monkeypatch.setattr(verification_agents, "get_verification_grader", lambda: agent)

    with pytest.raises(LLMGradingError) as caught:
        asyncio.run(grade_evidence("grade this"))
    assert caught.value.error_type == "llm.unknown"
    assert str(caught.value) == "llm.unknown"


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
