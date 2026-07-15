"""Deterministic graders for shared verification tasks."""

from __future__ import annotations

from learn_to_cloud_shared.verification.tasks.base import (
    GradingResult,
    VerificationTask,
    require_file_presence_grader,
)


def grade_file_presence_task(
    task: VerificationTask,
    file_paths: list[str],
    file_contents: dict[str, str] | None = None,
) -> GradingResult:
    """Grade a task by file presence and optional content indicators."""
    grader = require_file_presence_grader(task)
    file_contents = file_contents or {}
    normalized_paths = {path.lower(): path for path in file_paths}

    missing_all = [
        path
        for path in grader.required_all
        if not _path_present(path, normalized_paths)
    ]
    if missing_all:
        return GradingResult(
            task_id=task.id,
            task_name=task.name,
            passed=False,
            feedback=f"Missing required file(s): {', '.join(missing_all)}",
            grader_kind=grader.kind,
            failure_reason="required_file_missing",
        )

    if grader.required_any and not any(
        _path_present(path, normalized_paths) for path in grader.required_any
    ):
        return GradingResult(
            task_id=task.id,
            task_name=task.name,
            passed=False,
            feedback=(
                f"Missing one of the required file(s): {', '.join(grader.required_any)}"
            ),
            grader_kind=grader.kind,
            failure_reason="required_file_missing",
        )

    combined_content = "\n".join(file_contents.values()).lower()
    missing_indicators = [
        indicator
        for indicator in grader.content_indicators
        if indicator.lower() not in combined_content
    ]
    if missing_indicators:
        return GradingResult(
            task_id=task.id,
            task_name=task.name,
            passed=False,
            feedback=(
                "Missing expected content indicator(s): "
                f"{', '.join(missing_indicators)}"
            ),
            grader_kind=grader.kind,
            failure_reason="content_indicator_missing",
        )

    return GradingResult(
        task_id=task.id,
        task_name=task.name,
        passed=True,
        feedback=f"Found required evidence for {task.name}.",
        grader_kind=grader.kind,
        evidence_refs=list(normalized_paths.values()),
    )


def _path_present(pattern: str, normalized_paths: dict[str, str]) -> bool:
    normalized_pattern = pattern.lower()
    if normalized_pattern.endswith("/"):
        return any(path.startswith(normalized_pattern) for path in normalized_paths)
    return normalized_pattern in normalized_paths
