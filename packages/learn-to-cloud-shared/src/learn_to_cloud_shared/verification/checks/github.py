"""Typed github checks for verification workflows."""

from __future__ import annotations

from learn_to_cloud_shared.schemas import ValidationResult
from learn_to_cloud_shared.verification.checks.common import (
    missing_repository_result,
    validation_step_result,
)
from learn_to_cloud_shared.verification.ci_status import verify_ci_status
from learn_to_cloud_shared.verification.core import StepContext, StepResult
from learn_to_cloud_shared.verification.github_profile import (
    validate_profile_readme,
    validate_repo_fork,
)


async def check_github_ci_passing(context: StepContext) -> StepResult:
    """Gate on full capstone verification for the fork's current main commit."""
    target = context.repository
    if target is None:
        return missing_repository_result()
    result = await verify_ci_status(target.owner, target.repo)
    return validation_step_result(result)


async def check_profile_readme(context: StepContext) -> StepResult:
    """Deterministic Phase 0 gate: the profile README repo resolves."""
    target = context.repository
    if target is None:
        return StepResult(
            passed=False,
            stop_on_fail=True,
            validation_result=ValidationResult(
                is_valid=False,
                message=(
                    "Requirement configuration error: could not resolve GitHub target"
                ),
                username_match=True,
                repo_exists=False,
            ),
        )
    result = await validate_profile_readme(target)
    return validation_step_result(result)


async def check_repo_fork(context: StepContext) -> StepResult:
    """Deterministic Phase 1/2 gate: the learner's repo forks the upstream."""
    target = context.repository
    if target is None:
        return StepResult(
            passed=False,
            stop_on_fail=True,
            validation_result=ValidationResult(
                is_valid=False,
                message=(
                    "Requirement configuration error: could not resolve GitHub target"
                ),
                username_match=True,
                repo_exists=False,
            ),
        )
    result = await validate_repo_fork(target)
    return validation_step_result(result)
