"""Typed conversion of stored rubric feedback for templates."""

from dataclasses import dataclass
from typing import TypedDict


class FeedbackTaskContext(TypedDict):
    name: str
    passed: bool
    message: str
    next_steps: str


@dataclass(frozen=True, slots=True)
class VerificationFeedbackContext:
    tasks: list[FeedbackTaskContext]
    passed: int


def convert_feedback(
    feedback_json: list[dict] | None,
) -> VerificationFeedbackContext | None:
    """Convert persisted task results to the shared feedback view shape."""
    if not feedback_json:
        return None
    tasks: list[FeedbackTaskContext] = [
        {
            "name": str(task.get("task_name") or ""),
            "passed": bool(task.get("passed", False)),
            "message": str(task.get("feedback") or ""),
            "next_steps": str(task.get("next_steps") or ""),
        }
        for task in feedback_json
    ]
    return VerificationFeedbackContext(
        tasks=tasks,
        passed=sum(1 for task in tasks if task["passed"]),
    )
