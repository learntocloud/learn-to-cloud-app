"""Deterministic graders for shared verification tasks."""

from __future__ import annotations

from learn_to_cloud_shared.verification.tasks.base import (
    GradingResult,
    VerificationTask,
    require_file_presence_grader,
    require_indicator_grader,
)


def grade_indicator_task(
    task: VerificationTask,
    file_contents: list[str],
) -> GradingResult:
    """Grade a task by deterministic substring indicators."""
    grader = require_indicator_grader(task)
    combined = "\n".join(file_contents) if file_contents else ""
    combined_lower = combined.lower()

    for indicator in grader.fail_indicators:
        if indicator.lower() in combined_lower:
            return GradingResult(
                task_id=task.id,
                task_name=task.name,
                passed=False,
                feedback=f"Found disallowed pattern: {indicator}",
                next_steps=f"Remove or replace: {indicator}",
                grader_kind=grader.kind,
                failure_reason="fail_indicator_matched",
            )

    pass_indicators = grader.pass_indicators
    min_count = grader.min_pass_count

    if not pass_indicators:
        return GradingResult(
            task_id=task.id,
            task_name=task.name,
            passed=True,
            feedback="No specific indicators required.",
            grader_kind=grader.kind,
        )

    matched = [
        indicator
        for indicator in pass_indicators
        if indicator.lower() in combined_lower
    ]

    if len(matched) >= min_count:
        return GradingResult(
            task_id=task.id,
            task_name=task.name,
            passed=True,
            feedback=(
                f"Found {len(matched)}/{len(pass_indicators)} "
                "implementation indicators."
            ),
            grader_kind=grader.kind,
            evidence_refs=matched,
        )

    missing = [indicator for indicator in pass_indicators if indicator not in matched]
    return GradingResult(
        task_id=task.id,
        task_name=task.name,
        passed=False,
        feedback=(
            f"Found {len(matched)}/{len(pass_indicators)} indicators "
            f"(need at least {min_count}). "
            f"Missing: {', '.join(missing[:5])}"
        ),
        next_steps=(
            f"Add the missing implementation. Look for: {missing[0]}"
            if missing
            else "Review the requirements."
        ),
        grader_kind=grader.kind,
        failure_reason="insufficient_pass_indicators",
        evidence_refs=matched,
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
