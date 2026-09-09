"""Career reflection validation and grading preparation."""

from __future__ import annotations

from learn_to_cloud_shared.schemas import ValidationResult
from learn_to_cloud_shared.submission_values import TextValue
from learn_to_cloud_shared.verification.core import StepContext, StepResult
from learn_to_cloud_shared.verification.evidence import collect_submitted_text_evidence
from learn_to_cloud_shared.verification.tasks.base import VerificationTask


async def check_career_reflection(
    context: StepContext,
    *,
    task: VerificationTask,
) -> StepResult:
    """Prepare the validated reflection text for rubric grading."""
    submitted_value = context.submitted_value
    if not isinstance(submitted_value, TextValue):
        raise TypeError("Career reflection check requires a text value")
    bundle = collect_submitted_text_evidence(
        task, submitted_value.text, "career-reflection.md"
    )
    return StepResult(
        passed=True,
        validation_result=ValidationResult(
            is_valid=True,
            message="Reflection received. Reviewing your answers.",
        ),
        evidence=[bundle],
        grading_task=task,
    )
