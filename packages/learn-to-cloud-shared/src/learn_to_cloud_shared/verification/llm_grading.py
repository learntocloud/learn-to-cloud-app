"""Apply durable LLM grading decisions to verification job results.

Migrated engine profiles record their grading requests on the verify result
via the engine's rubric-review steps, so evidence collection and prompt
assembly live in the engine, not here. This module now only merges the
grader's decisions back into the run result and formats grader-outage and
content-filter results.
"""

from __future__ import annotations

from dataclasses import replace

from learn_to_cloud_shared.verification.grading_requests import (
    LLMGradingDecisionPayload,
    LLMGradingRequest,
)
from learn_to_cloud_shared.verification.tasks import (
    GradingResult,
    LLMGradingDecision,
    RubricCriterion,
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
    "validate_llm_grading_decision",
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


def validate_llm_grading_decision(
    task: VerificationTask,
    decision: LLMGradingDecision,
    allowed_evidence_refs: list[str],
) -> None:
    """Validate a model decision against its task-specific rubric."""
    criteria_by_id = {
        criterion.id: criterion
        for criterion in task.criteria
        if isinstance(criterion, RubricCriterion)
    }
    result_ids = [result.criterion_id for result in decision.criterion_results]
    if len(result_ids) != len(set(result_ids)):
        raise ValueError("Criterion results contain duplicate IDs")
    if set(result_ids) != set(criteria_by_id):
        raise ValueError("Criterion results do not match the configured rubric")

    allowed_refs = set(allowed_evidence_refs)
    all_refs = list(decision.evidence_refs)
    required_unmet = False
    for result in decision.criterion_results:
        criterion = criteria_by_id[result.criterion_id]
        if criterion.kind == "required" and result.status == "not_applicable":
            raise ValueError("Required criteria cannot be not applicable")
        if criterion.kind == "required" and result.status != "met":
            required_unmet = True
        if (
            criterion.kind == "required"
            and result.status == "not_met"
            and not result.next_steps.strip()
        ):
            raise ValueError("Unmet required criteria need remediation")
        all_refs.extend(result.evidence_refs)

    if decision.passed and required_unmet:
        raise ValueError("A passing decision cannot have unmet required criteria")
    if any(reference not in allowed_refs for reference in all_refs):
        raise ValueError("Decision contains an unknown evidence reference")


def llm_grading_unavailable_result(
    run_result: VerificationRunResult,
    *,
    error_type: str,
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
                "problem on our end, not yours. Please submit again later."
            ),
            "verification_completed": False,
        }
    )
    return replace(
        run_result,
        validation_result=validation_result,
        llm_error_type=error_type,
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
            "verification_completed": True,
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
    criteria_by_id = {
        criterion.id: criterion
        for criterion in task.criteria
        if isinstance(criterion, RubricCriterion)
    }
    criterion_results = [
        result.model_copy(
            update={
                "label": criteria_by_id[result.criterion_id].label,
                "kind": criteria_by_id[result.criterion_id].kind,
            }
        )
        for result in decision.criterion_results
    ]

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
        criterion_results=criterion_results,
    )
