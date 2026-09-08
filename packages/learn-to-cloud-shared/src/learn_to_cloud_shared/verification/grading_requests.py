"""Typed rubric requests and decisions with validated prompt builders."""

from __future__ import annotations

import json

from pydantic import Field, ValidationError

from learn_to_cloud_shared.schemas import FrozenModel, ValidationResult
from learn_to_cloud_shared.verification.evidence import (
    EvidenceError,
    validate_evidence_bundle,
)
from learn_to_cloud_shared.verification.tasks import (
    LLMGradingDecision,
    RubricCriterion,
    VerificationTask,
)
from learn_to_cloud_shared.verification.tasks.base import EvidenceBundle


class LLMGradingRequest(FrozenModel):
    """One self-contained rubric grading request."""

    task: VerificationTask
    message: str
    allowed_evidence_refs: list[str] = Field(default_factory=list)


class LLMGradingDecisionPayload(FrozenModel):
    """A structured LLM decision paired with its task definition."""

    task: VerificationTask
    decision: LLMGradingDecision


def _task_payload(task: VerificationTask) -> dict[str, object]:
    grader = task.grader
    return {
        "id": task.id,
        "name": task.name,
        "criteria": [
            criterion.model_dump(mode="json")
            if isinstance(criterion, RubricCriterion)
            else criterion
            for criterion in task.criteria
        ],
        "grading_instructions": task.grading_instructions,
        "rubric_id": grader.rubric_id,
        "prompt_version": grader.prompt_version,
        "passing_score": grader.passing_score,
        "evidence_contract": task.evidence.model_dump(mode="json"),
    }


def _validated_evidence_payload(
    task: VerificationTask,
    evidence: dict[str, object],
    deterministic_result: ValidationResult,
) -> dict[str, object]:
    if (
        not deterministic_result.verification_completed
        or not deterministic_result.is_valid
    ):
        raise EvidenceError("evidence.selection")
    try:
        bundle = EvidenceBundle.model_validate(evidence)
    except ValidationError as exc:
        raise EvidenceError("evidence.selection") from exc
    validate_evidence_bundle(task, bundle)
    payload = bundle.model_dump(mode="json")
    payload["optional_presence"] = {
        path: any(item.path == path for item in bundle.items)
        for path in task.evidence.optional_files
    }
    return payload


def validate_grading_request(request: LLMGradingRequest) -> None:
    """Recheck prompt evidence immediately before invoking the grader."""
    try:
        payload = json.loads(request.message.split("\n\n", 1)[1])
        result = ValidationResult.model_validate(payload["deterministic_result"])
        evidence = payload["evidence"]
        message_task = payload["task"]
        expected_task = _task_payload(request.task)
        if message_task != expected_task:
            raise EvidenceError("evidence.selection")
        validated = _validated_evidence_payload(request.task, evidence, result)
        bundle = EvidenceBundle.model_validate(validated)
        allowed_refs = {item.path for item in bundle.items}
        allowed_refs.update(task.task_name for task in result.task_results or [])
        if set(request.allowed_evidence_refs) != allowed_refs:
            raise EvidenceError("evidence.selection")
    except (IndexError, KeyError, TypeError, ValueError) as exc:
        if isinstance(exc, EvidenceError):
            raise
        raise EvidenceError("evidence.selection") from exc


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
        "evidence": _validated_evidence_payload(task, evidence, deterministic_result),
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
        "evidence": _validated_evidence_payload(task, evidence, deterministic_result),
    }
    return (
        "Grade this Learn to Cloud verification task using only the JSON payload. "
        "The evidence is the learner's own free-text reflection answers. "
        "Return a structured grading decision that follows the configured schema.\n\n"
        f"{json.dumps(payload, sort_keys=True)}"
    )
