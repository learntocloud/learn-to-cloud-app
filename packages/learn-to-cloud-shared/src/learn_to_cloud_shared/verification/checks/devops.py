"""Typed devops checks for verification workflows."""

from __future__ import annotations

from learn_to_cloud_shared.verification.checks.common import (
    missing_repository_result,
    validation_step_result,
)
from learn_to_cloud_shared.verification.core import CheckParams, StepContext, StepResult
from learn_to_cloud_shared.verification.devops_analysis import (
    verify_required_devops_files,
)
from learn_to_cloud_shared.verification.ghcr import verify_public_ghcr_image


class DevopsRequiredFilesParams(CheckParams):
    """Params for the Phase 5 required-files gate."""

    check_name = "devops_required_files"


async def _check_devops_required_files(
    context: StepContext,
    params: CheckParams,
) -> StepResult:
    """Gate on the prescribed Phase 5 repository paths."""
    target = context.repository
    if target is None:
        return missing_repository_result()
    result = await verify_required_devops_files(
        target.owner,
        target.repo,
        context.repo_files,
    )
    return validation_step_result(result)


class PublicGhcrImageParams(CheckParams):
    """Params for the Phase 5 public GHCR image gate."""

    check_name = "public_ghcr_image"


async def _check_public_ghcr_image(
    context: StepContext,
    params: CheckParams,
) -> StepResult:
    """Gate on the learner's public ``journal-api:latest`` GHCR manifest."""
    target = context.repository
    if target is None:
        return missing_repository_result()
    result = await verify_public_ghcr_image(target.owner)
    return validation_step_result(result)
