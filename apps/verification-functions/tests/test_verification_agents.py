"""Tests for content-safety handling in the verification grader adapter."""

from __future__ import annotations

import asyncio

import httpx
import openai
import pytest
import verification_agents
from verification_agents import (
    ContentFilteredError,
    _find_content_filter_error,
    grade_evidence,
)


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


def test_grade_evidence_reraises_other_errors(monkeypatch) -> None:
    agent = _FakeAgent(RuntimeError("network down"))
    monkeypatch.setattr(verification_agents, "get_verification_grader", lambda: agent)

    with pytest.raises(RuntimeError, match="network down"):
        asyncio.run(grade_evidence("grade this"))
