"""Typed deployment architecture checks for verification workflows."""

from __future__ import annotations

import httpx

from learn_to_cloud_shared.submission_values import TextValue
from learn_to_cloud_shared.verification.checks.common import validation_step_result
from learn_to_cloud_shared.verification.core import CheckParams, StepContext, StepResult
from learn_to_cloud_shared.verification.deployment_architecture import (
    collect_deployment_architecture_evidence,
    deployment_architecture_task,
    validate_deployment_architecture,
)
from learn_to_cloud_shared.verification.evidence import EvidenceError
from learn_to_cloud_shared.verification.github_errors import (
    GitHubServerError,
    github_error_to_result,
)
from learn_to_cloud_shared.verification.repo_files import default_repo_files
from learn_to_cloud_shared.verification.tasks.base import VerificationTask


class DeploymentArchitectureGateParams(CheckParams):
    """Params for the Phase 4 ``deployment_architecture_gate`` (no config).

    The gate reads the description length and deploy-script path from the
    requirement's ``type_config`` at runtime, so it carries no data.
    """

    check_name = "deployment_architecture_gate"


async def _check_deployment_architecture_gate(
    context: StepContext,
    params: CheckParams,
) -> StepResult:
    """Phase 4 gate: description meets min length and ``deploy.sh`` exists."""
    submitted_value = context.submitted_value
    if not isinstance(submitted_value, TextValue):
        raise TypeError("Deployment architecture check requires a text value")
    result = await validate_deployment_architecture(
        context.job.requirement,
        submitted_value.text,
        context.repository,
        context.repo_files,
    )
    return validation_step_result(result)


class DeploymentArchitectureReviewParams(CheckParams):
    """Params for the Phase 4 ``deployment_architecture_review`` rubric step.

    Bundles the learner's forked ``deploy.sh`` with their architecture
    description for the LLM rubric grader.
    """

    check_name = "deployment_architecture_review"
    task: VerificationTask


async def _check_deployment_architecture_review(
    context: StepContext,
    params: CheckParams,
) -> StepResult:
    """Bundle the fork's ``deploy.sh`` and the architecture description.

    Like ``llm_rubric_review`` but its evidence is a repo file plus the
    learner's free-text description, not a set of exact repository paths.
    """
    assert isinstance(params, DeploymentArchitectureReviewParams)
    target = context.repository
    if target is None:
        raise EvidenceError("evidence.configuration")
    deploy_script_path = getattr(
        context.job.requirement.type_config, "deploy_script_path", None
    )
    if deploy_script_path is None:
        raise EvidenceError("evidence.configuration")
    task = deployment_architecture_task(params.task, deploy_script_path)
    submitted_value = context.submitted_value
    if not isinstance(submitted_value, TextValue):
        raise TypeError("Deployment architecture review requires a text value")
    try:
        bundle = await collect_deployment_architecture_evidence(
            target.owner,
            target.repo,
            submitted_value.text,
            task,
            deploy_script_path=deploy_script_path,
            repo_files=context.repo_files or default_repo_files(),
        )
    except (GitHubServerError, httpx.HTTPStatusError, httpx.RequestError) as exc:
        return StepResult(
            passed=False,
            stop_on_fail=True,
            validation_result=github_error_to_result(
                exc, event="deployment_architecture.repo_file_error"
            ),
        )
    return StepResult(
        passed=True,
        stop_on_fail=False,
        evidence=[bundle],
        grading_task=task,
    )
