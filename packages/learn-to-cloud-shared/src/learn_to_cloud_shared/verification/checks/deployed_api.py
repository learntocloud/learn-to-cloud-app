"""Typed deployed api checks for verification workflows."""

from __future__ import annotations

from learn_to_cloud_shared.submission_values import DeployedUrlValue
from learn_to_cloud_shared.verification.checks.common import validation_step_result
from learn_to_cloud_shared.verification.core import CheckParams, StepContext, StepResult
from learn_to_cloud_shared.verification.deployed_api import validate_deployed_api


class DeployedApiCheckParams(CheckParams):
    """Params for the deterministic ``deployed_api_check`` (no config).

    The check probes the submitted base URL's health surface; the target URL
    is the submitted value, so it carries no data.
    """

    check_name = "deployed_api_check"


async def _check_deployed_api(
    context: StepContext,
    params: CheckParams,
) -> StepResult:
    """Deterministic Phase 4 gate: probe the submitted API base URL."""
    submitted_value = context.submitted_value
    if not isinstance(submitted_value, DeployedUrlValue):
        raise TypeError("Deployed API check requires a deployed URL value")
    result = await validate_deployed_api(submitted_value.url)
    return validation_step_result(result)
