"""Typed career checks for verification workflows."""

from __future__ import annotations

from learn_to_cloud_shared.submission_values import TextValue
from learn_to_cloud_shared.verification.career_reflection import (
    collect_career_reflection_evidence,
    validate_career_reflection,
)
from learn_to_cloud_shared.verification.checks.common import validation_step_result
from learn_to_cloud_shared.verification.core import CheckParams, StepContext, StepResult
from learn_to_cloud_shared.verification.tasks.base import VerificationTask


class CareerReflectionGateParams(CheckParams):
    """Params for the Phase 7 ``career_reflection_gate`` (no config).

    The gate only rejects empty submissions; the rubric does the real grading.
    """

    check_name = "career_reflection_gate"


async def _check_career_reflection_gate(
    context: StepContext,
    params: CheckParams,
) -> StepResult:
    """Deterministic Phase 7 gate: reject empty reflection submissions."""
    submitted_value = context.submitted_value
    if not isinstance(submitted_value, TextValue):
        raise TypeError("Career reflection check requires a text value")
    result = validate_career_reflection(submitted_value.text)
    return validation_step_result(result)


class CareerReflectionReviewParams(CheckParams):
    """Params for the Phase 7 ``career_reflection_review`` text rubric step.

    Bundles the learner's free-text reflection as evidence; carries the rubric
    ``task``. Text-only, so the grading request uses the no-repo prompt.
    """

    check_name = "career_reflection_review"
    task: VerificationTask


async def _check_career_reflection_review(
    context: StepContext,
    params: CheckParams,
) -> StepResult:
    """Bundle the learner's free-text reflection for text rubric grading."""
    assert isinstance(params, CareerReflectionReviewParams)
    submitted_value = context.submitted_value
    if not isinstance(submitted_value, TextValue):
        raise TypeError("Career reflection review requires a text value")
    bundle = collect_career_reflection_evidence(submitted_value.text, params.task)
    return StepResult(
        passed=True,
        stop_on_fail=False,
        evidence=[bundle],
        grading_task=params.task,
    )
