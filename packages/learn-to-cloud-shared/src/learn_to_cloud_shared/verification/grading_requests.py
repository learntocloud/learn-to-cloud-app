"""LLM grading request/decision transport plus shared prompt builders.

Kept dependency-light on purpose: it imports only schemas and task
definitions, never ``verification_job_executor``. That lets the executor
carry :class:`LLMGradingRequest`s on ``VerificationRunResult`` (so the engine
can record grading requests on the verify result) without an import cycle,
and lets both the engine and the legacy grading probe build the LLM prompt
from one place.
"""

from __future__ import annotations

import json

from learn_to_cloud_shared.schemas import FrozenModel, ValidationResult
from learn_to_cloud_shared.verification.tasks import (
    LLMGradingDecision,
    VerificationTask,
    require_llm_rubric_grader,
)


class LLMGradingRequest(FrozenModel):
    """One durable agent grading request."""

    task: VerificationTask
    message: str
    thread_id: str


class LLMGradingDecisionPayload(FrozenModel):
    """A structured LLM decision paired with its task definition."""

    task: VerificationTask
    decision: LLMGradingDecision


def _task_payload(task: VerificationTask) -> dict[str, object]:
    grader = require_llm_rubric_grader(task)
    return {
        "id": task.id,
        "name": task.name,
        "criteria": task.criteria,
        "rubric_id": grader.rubric_id,
        "prompt_version": grader.prompt_version,
        "passing_score": grader.passing_score,
    }


def build_repo_rubric_message(
    *,
    requirement_slug: str,
    requirement_name: str,
    deterministic_result: ValidationResult,
    owner: str,
    repo: str,
    task: VerificationTask,
    evidence: dict[str, object],
) -> str:
    """Build the LLM prompt for a repository-backed rubric review."""
    payload = {
        "requirement": {"id": requirement_slug, "name": requirement_name},
        "task": _task_payload(task),
        "repository": {"owner": owner, "name": repo},
        "deterministic_result": deterministic_result.model_dump(mode="json"),
        "evidence": evidence,
    }
    return (
        "Grade this Learn to Cloud verification task using only the JSON payload. "
        "Return a structured grading decision that follows the configured schema.\n\n"
        f"{json.dumps(payload, sort_keys=True)}"
    )


def build_text_rubric_message(
    *,
    requirement_slug: str,
    requirement_name: str,
    deterministic_result: ValidationResult,
    task: VerificationTask,
    evidence: dict[str, object],
) -> str:
    """Build the LLM prompt for a free-text (no-repo) rubric review."""
    payload = {
        "requirement": {"id": requirement_slug, "name": requirement_name},
        "task": _task_payload(task),
        "deterministic_result": deterministic_result.model_dump(mode="json"),
        "evidence": evidence,
    }
    return (
        "Grade this Learn to Cloud verification task using only the JSON payload. "
        "The evidence is the learner's own free-text reflection answers. "
        "Return a structured grading decision that follows the configured schema.\n\n"
        f"{json.dumps(payload, sort_keys=True)}"
    )
