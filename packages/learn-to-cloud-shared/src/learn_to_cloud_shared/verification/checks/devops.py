"""Phase 5 delivery pipeline check."""

from learn_to_cloud_shared.verification.checks.common import (
    missing_repository_result,
    validation_step_result,
)
from learn_to_cloud_shared.verification.core import StepContext, StepResult
from learn_to_cloud_shared.verification.devops_analysis import verify_devops_pipeline


async def check_devops_pipeline(context: StepContext) -> StepResult:
    """Verify the current commit's delivery run without collecting source files."""
    target = context.repository
    if target is None:
        return missing_repository_result()
    result = await verify_devops_pipeline(target.owner, target.repo)
    return validation_step_result(result)
