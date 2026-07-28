"""Apply durable LLM grading decisions to verification job results.

Migrated engine profiles record their grading requests on the verify result
via the engine's rubric-review steps, so evidence collection and prompt
assembly live in the engine, not here. This module now only merges the
grader's decisions back into the run result and formats grader-outage and
content-filter results.
"""

from __future__ import annotations

from learn_to_cloud_shared.verification.grading_requests import (
    LLMGradingDecisionPayload,
    LLMGradingRequest,
)
from learn_to_cloud_shared.verification.tasks import (
    GradingResult,
    LLMGradingDecision,
    VerificationTask,
    require_llm_rubric_grader,
)
from learn_to_cloud_shared.verification_workflow import (
    VerificationRunResult,
)

__all__ = [
    "LLMGradingDecisionPayload",
    "LLMGradingRequest",
    "apply_llm_grading_decisions",
    "llm_grading_content_filtered_result",
    "llm_grading_unavailable_result",
]


def apply_llm_grading_decisions(
    run_result: VerificationRunResult,
    decisions: list[LLMGradingDecisionPayload],
) -> VerificationRunResult:
    """Merge LLM task decisions into the validation result."""
    if not decisions:
        return run_result

    task_results = list(run_result.validation_result.task_results or [])
    grading_results = [
        _decision_to_grading_result(payload.task, payload.decision)
        for payload in decisions
    ]
    task_results.extend(result.to_task_result() for result in grading_results)

    llm_passed = all(result.passed for result in grading_results)
    is_valid = run_result.validation_result.is_valid and llm_passed
    message = run_result.validation_result.message
    if run_result.validation_result.is_valid and not llm_passed:
        message = "LLM rubric review failed. Review the task feedback and try again."

    validation_result = run_result.validation_result.model_copy(
        update={
            "is_valid": is_valid,
            "message": message,
            "task_results": task_results,
        }
    )
    return VerificationRunResult(
        attempt=run_result.attempt,
        validation_result=validation_result,
        grading_disposition=run_result.grading_disposition,
    )


def llm_grading_unavailable_result(
    run_result: VerificationRunResult,
) -> VerificationRunResult:
    """Return a server-error validation result for LLM grader failures.

    The user-facing message stays generic; callers are responsible for
    recording the real cause in telemetry.
    """
    validation_result = run_result.validation_result.model_copy(
        update={
            "is_valid": False,
            "message": (
                "Automated grading is temporarily unavailable. This is a "
                "problem on our end, not yours. Please report it so we can "
                "fix it."
            ),
            "verification_completed": False,
        }
    )
    return VerificationRunResult(
        attempt=run_result.attempt,
        validation_result=validation_result,
        grading_disposition=run_result.grading_disposition,
    )


def llm_grading_content_filtered_result(
    run_result: VerificationRunResult,
) -> VerificationRunResult:
    """Return an actionable result when content safety blocked every retry.

    Azure's safety filter occasionally blocks a submission's free text. When
    it blocks every retry the cause is usually phrasing that looks like
    instructions or code, so the message asks the learner to rephrase and
    try again rather than blaming our systems.
    """
    validation_result = run_result.validation_result.model_copy(
        update={
            "is_valid": False,
            "message": (
                "We could not automatically review your answers because they "
                "tripped our content safety filter. This sometimes happens "
                "with certain phrasing. Please rewrite your answers in plain "
                "language, avoiding anything that reads like commands, code, "
                "or instructions, and submit again. If it keeps happening, "
                "report it so we can help."
            ),
            "verification_completed": False,
        }
    )
    return VerificationRunResult(
        attempt=run_result.attempt,
        validation_result=validation_result,
        grading_disposition=run_result.grading_disposition,
    )


def _decision_to_grading_result(
    task: VerificationTask,
    decision: LLMGradingDecision,
) -> GradingResult:
    grader = require_llm_rubric_grader(task)
    passed = decision.passed and decision.score >= grader.passing_score
    failure_reason = decision.failure_reason
    if decision.passed and not passed:
        failure_reason = "score_below_passing_threshold"

    return GradingResult(
        task_id=task.id,
        task_name=task.name,
        passed=passed,
        feedback=decision.feedback,
        next_steps=decision.next_steps,
        grader_kind=grader.kind,
        failure_reason=failure_reason,
        score=decision.score,
        confidence=decision.confidence,
        rubric_version=grader.rubric_id,
        evidence_refs=decision.evidence_refs,
    )
