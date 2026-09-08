"""Career reflection validation and grading preparation."""

from __future__ import annotations

from learn_to_cloud_shared.submission_values import TextValue
from learn_to_cloud_shared.verification.career_reflection import (
    collect_career_reflection_evidence,
    validate_career_reflection,
)
from learn_to_cloud_shared.verification.checks.common import validation_step_result
from learn_to_cloud_shared.verification.core import StepContext, StepResult
from learn_to_cloud_shared.verification.tasks.base import VerificationTask


async def check_career_reflection(
    context: StepContext,
    *,
    task: VerificationTask,
) -> StepResult:
    """Reject empty reflections and prepare valid text for rubric grading."""
    submitted_value = context.submitted_value
    if not isinstance(submitted_value, TextValue):
        raise TypeError("Career reflection check requires a text value")
    result = validate_career_reflection(submitted_value.text)
    if not result.is_valid or not result.verification_completed:
        return validation_step_result(result)
    bundle = collect_career_reflection_evidence(submitted_value.text, task)
    return StepResult(
        passed=True,
        validation_result=result,
        evidence=[bundle],
        grading_task=task,
    )
