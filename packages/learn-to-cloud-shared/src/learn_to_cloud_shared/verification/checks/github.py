"""Typed github checks for verification workflows."""

from __future__ import annotations

from learn_to_cloud_shared.schemas import ValidationResult
from learn_to_cloud_shared.verification.checks.common import (
    missing_repository_result,
    validation_step_result,
)
from learn_to_cloud_shared.verification.ci_status import verify_ci_status
from learn_to_cloud_shared.verification.core import CheckParams, StepContext, StepResult
from learn_to_cloud_shared.verification.github_profile import (
    validate_profile_readme,
    validate_repo_fork,
)


class CIStatusParams(CheckParams):
    """Params for the ``github_ci_passing`` gate (workflow file is fixed)."""

    check_name = "github_ci_passing"


async def _check_github_ci_passing(
    context: StepContext,
    params: CheckParams,
) -> StepResult:
    """Gate on full capstone verification for the fork's current main commit."""
    target = context.repository
    if target is None:
        return missing_repository_result()
    result = await verify_ci_status(target.owner, target.repo)
    return validation_step_result(result)


class ProfileReadmeCheckParams(CheckParams):
    """Params for the deterministic Phase 0 ``profile_readme_check`` (no config).

    The check confirms the learner's ``<username>/<username>`` profile README
    repo resolves; the target is built from the username, so it carries no data.
    """

    check_name = "profile_readme_check"


async def _check_profile_readme(
    context: StepContext,
    params: CheckParams,
) -> StepResult:
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


class RepoForkCheckParams(CheckParams):
    """Params for the deterministic Phase 1/2 ``repo_fork_check`` (no config).

    The check confirms the learner's repo is a fork of the required upstream;
    fork identity and upstream come from the target, so it carries no data.
    """

    check_name = "repo_fork_check"


async def _check_repo_fork(
    context: StepContext,
    params: CheckParams,
) -> StepResult:
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
