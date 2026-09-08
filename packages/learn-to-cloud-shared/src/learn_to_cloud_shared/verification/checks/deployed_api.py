"""Typed deployed api checks for verification workflows."""

from __future__ import annotations

from learn_to_cloud_shared.submission_values import DeployedUrlValue
from learn_to_cloud_shared.verification.checks.common import validation_step_result
from learn_to_cloud_shared.verification.core import StepContext, StepResult
from learn_to_cloud_shared.verification.deployed_api import validate_deployed_api


async def check_deployed_api(context: StepContext) -> StepResult:
    """Deterministic Phase 4 gate: probe the submitted API base URL."""
    submitted_value = context.submitted_value
    if not isinstance(submitted_value, DeployedUrlValue):
        raise TypeError("Deployed API check requires a deployed URL value")
    result = await validate_deployed_api(submitted_value.url)
    return validation_step_result(result)
