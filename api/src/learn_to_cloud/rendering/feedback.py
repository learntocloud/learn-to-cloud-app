"""Learner-facing verification feedback and safe repository evidence links."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import PurePosixPath
from typing import Literal
from urllib.parse import quote, urlparse


def incomplete_verification_message(cause: str | None) -> str:
    """Explain an incomplete outcome alongside its saved learner-safe cause."""
    explanation = (
        "Verification stopped before it could finish. "
        "Your work was not judged to have failed."
    )
    recovery = (
        "You can try again. If this keeps happening, report the issue. "
        "You do not need to change your work to fix a verification-service problem."
    )
    return " ".join(part for part in (explanation, cause, recovery) if part)


@dataclass(frozen=True, slots=True)
class FeedbackEvidenceContext:
    """One safe evidence label with an optional repository link."""

    label: str
    url: str | None = None


@dataclass(frozen=True, slots=True)
class FeedbackCriterionContext:
    """Learner-facing rubric criterion feedback."""

    id: str
    label: str
    kind: Literal["required", "quality", "bonus"]
    status: Literal["met", "not_met", "not_applicable"]
    explanation: str
    next_steps: str
    evidence: tuple[FeedbackEvidenceContext, ...]


@dataclass(frozen=True, slots=True)
class FeedbackTaskContext:
    """One deterministic task or structured rubric review."""

    name: str
    passed: bool
    message: str
    next_steps: str
    criteria: tuple[FeedbackCriterionContext, ...]


def feedback_tasks_and_passed(
    feedback: dict[str, object] | None,
) -> tuple[list[FeedbackTaskContext], int]:
    """Convert stored feedback into typed tasks and a passed count."""
    if not feedback:
        return [], 0
    raw_tasks = feedback.get("tasks", [])
    if not isinstance(raw_tasks, list):
        return [], 0
    tasks = [
        FeedbackTaskContext(
            name=str(task.get("name", "")),
            passed=bool(task.get("passed", False)),
            message=str(task.get("message", "")),
            next_steps=str(task.get("next_steps", "")),
            criteria=tuple(
                _feedback_criterion(criterion)
                for criterion in criteria
                if isinstance(criterion, dict)
            ),
        )
        for task in raw_tasks
        if isinstance(task, dict)
        and isinstance((criteria := task.get("criteria", [])), list)
    ]
    passed_value = feedback.get("passed", 0)
    passed = passed_value if isinstance(passed_value, int) else 0
    return tasks, passed


def _feedback_criterion(raw: object) -> FeedbackCriterionContext:
    if not isinstance(raw, dict):
        raise TypeError("Feedback criterion must be an object")
    kind = raw.get("kind", "required")
    if kind not in {"required", "quality", "bonus"}:
        kind = "required"
    status = raw.get("status", "not_met")
    if status not in {"met", "not_met", "not_applicable"}:
        status = "not_met"
    raw_refs = raw.get("evidence_refs", [])
    refs = raw_refs if isinstance(raw_refs, list) else []
    return FeedbackCriterionContext(
        id=str(raw.get("id", "")),
        label=str(raw.get("label", "")),
        kind=kind,
        status=status,
        explanation=str(raw.get("explanation", "")),
        next_steps=str(raw.get("next_steps", "")),
        evidence=tuple(
            FeedbackEvidenceContext(label=str(reference)) for reference in refs
        ),
    )


def prepare_card_feedback(
    feedback_tasks: list[FeedbackTaskContext] | None,
    feedback_passed: int,
    graded_url: str | None = None,
) -> tuple[list[FeedbackTaskContext], int]:
    """Attach safe evidence links when a graded repository URL is available."""
    tasks = feedback_tasks or []
    if graded_url:
        tasks = [_link_task_evidence(task, graded_url) for task in tasks]
    return tasks, feedback_passed


def _link_task_evidence(
    task: FeedbackTaskContext,
    repository_url: str,
) -> FeedbackTaskContext:
    return FeedbackTaskContext(
        name=task.name,
        passed=task.passed,
        message=task.message,
        next_steps=task.next_steps,
        criteria=tuple(
            FeedbackCriterionContext(
                id=criterion.id,
                label=criterion.label,
                kind=criterion.kind,
                status=criterion.status,
                explanation=criterion.explanation,
                next_steps=criterion.next_steps,
                evidence=tuple(
                    FeedbackEvidenceContext(
                        label=evidence.label,
                        url=_repository_evidence_url(
                            repository_url,
                            evidence.label,
                        ),
                    )
                    for evidence in criterion.evidence
                ),
            )
            for criterion in task.criteria
        ),
    )


def _repository_evidence_url(repository_url: str, reference: str) -> str | None:
    parsed = urlparse(repository_url)
    path_parts = [part for part in parsed.path.split("/") if part]
    if (
        parsed.scheme != "https"
        or parsed.netloc != "github.com"
        or len(path_parts) != 2
        or not reference
        or any(character.isspace() for character in reference)
    ):
        return None
    evidence_path = PurePosixPath(reference)
    if evidence_path.is_absolute() or ".." in evidence_path.parts:
        return None
    return f"{repository_url.rstrip('/')}/blob/HEAD/{quote(reference, safe='/')}"
