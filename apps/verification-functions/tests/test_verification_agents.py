"""Tests for content-safety handling in the verification grader adapter."""

from __future__ import annotations

import asyncio

import httpx
import openai
import pytest
import verification_agents
from learn_to_cloud_shared.verification.tasks import (
    CAREER_REFLECTION_RUBRIC_TASK,
    PHASE3_LLM_TASKS,
    PHASE4_LLM_TASKS,
    PHASE5_LLM_TASKS,
    PHASE6_LLM_TASKS,
    PHASE7_LLM_TASKS,
)

from verification_agents import (
    ContentFilteredError,
    _find_content_filter_error,
    grade_evidence,
)

ALL_LLM_RUBRIC_TASKS = [
    *PHASE3_LLM_TASKS,
    *PHASE4_LLM_TASKS,
    *PHASE5_LLM_TASKS,
    *PHASE6_LLM_TASKS,
    *PHASE7_LLM_TASKS,
]


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
        verification_agents,
        "get_verification_grader",
        lambda prompt_id, model_deployment: agent,
    )
    monkeypatch.setattr(
        verification_agents, "resolve_model_deployment", lambda task: "test-deploy"
    )

    with pytest.raises(ContentFilteredError):
        asyncio.run(grade_evidence(CAREER_REFLECTION_RUBRIC_TASK, "grade this"))


def test_grade_evidence_reraises_other_errors(monkeypatch) -> None:
    agent = _FakeAgent(RuntimeError("network down"))
    monkeypatch.setattr(
        verification_agents,
        "get_verification_grader",
        lambda prompt_id, model_deployment: agent,
    )
    monkeypatch.setattr(
        verification_agents, "resolve_model_deployment", lambda task: "test-deploy"
    )

    with pytest.raises(RuntimeError, match="network down"):
        asyncio.run(grade_evidence(CAREER_REFLECTION_RUBRIC_TASK, "grade this"))


def test_resolve_model_deployment_inherits_env_default(monkeypatch) -> None:
    monkeypatch.setenv("FOUNDRY_PROJECT_ENDPOINT", "https://example.test/")
    monkeypatch.setenv("FOUNDRY_MODEL_DEPLOYMENT_NAME", "gpt-5-mini-verifier")

    assert (
        verification_agents.resolve_model_deployment(CAREER_REFLECTION_RUBRIC_TASK)
        == "gpt-5-mini-verifier"
    )


def test_resolve_model_deployment_prefers_task_override(monkeypatch) -> None:
    monkeypatch.setenv("FOUNDRY_PROJECT_ENDPOINT", "https://example.test/")
    monkeypatch.setenv("FOUNDRY_MODEL_DEPLOYMENT_NAME", "gpt-5-mini-verifier")
    task = CAREER_REFLECTION_RUBRIC_TASK.model_copy(
        update={
            "grader": CAREER_REFLECTION_RUBRIC_TASK.grader.model_copy(
                update={"model_deployment": "gpt-5-large-verifier"}
            )
        }
    )

    assert verification_agents.resolve_model_deployment(task) == "gpt-5-large-verifier"


def test_all_shipped_tasks_inherit_the_deployed_model() -> None:
    """Task configs must not hardcode a deployment name that infra may rename."""
    for task in ALL_LLM_RUBRIC_TASKS:
        assert task.grader.model_deployment is None
