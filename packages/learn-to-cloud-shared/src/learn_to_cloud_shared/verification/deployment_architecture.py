"""Phase 4 capstone deployment-architecture verification.

Hybrid of Phase 7 (free-text + LLM rubric) and Phase 3 (repo-file evidence):
the learner writes an architecture description in the app, and the grader
fetches ``deploy.sh`` from their fork of the required repo. The deterministic
stage confirms the description meets a minimum length and that the deploy
script exists in the repo tree; the LLM rubric then judges whether the
description aligns with what the script actually provisions.
"""

from __future__ import annotations

import httpx

from learn_to_cloud_shared.github_repository_target import GitHubRepositoryTarget
from learn_to_cloud_shared.schemas import HandsOnRequirement, ValidationResult
from learn_to_cloud_shared.verification.evidence import (
    EvidenceError,
    apply_evidence_cap,
    record_evidence_decision,
    validate_evidence_policy,
)
from learn_to_cloud_shared.verification.github_errors import (
    GitHubServerError,
    github_error_to_result,
)
from learn_to_cloud_shared.verification.repo_files import RepoFiles, default_repo_files
from learn_to_cloud_shared.verification.tasks.base import (
    EvidenceBundle,
    VerificationTask,
)
from learn_to_cloud_shared.verification.tasks.phase4 import (
    DEPLOYMENT_ARCHITECTURE_RUBRIC_TASK,
)

_DESCRIPTION_EVIDENCE_PATH = "architecture-description.md"


def _deployment_architecture_config(requirement: HandsOnRequirement) -> object | None:
    """Return the deployment_architecture type_config, or None if misconfigured."""
    cfg = getattr(requirement, "type_config", None)
    if cfg is None or getattr(cfg, "deploy_script_path", None) is None:
        return None
    return cfg


def _top_level_shell_scripts(file_paths: list[str]) -> list[str]:
    """Return repo-root ``*.sh`` paths (no directory separator)."""
    return sorted(
        path for path in file_paths if "/" not in path and path.endswith(".sh")
    )


async def validate_deployment_architecture(
    requirement: HandsOnRequirement,
    description: str,
    target: GitHubRepositoryTarget | None,
    repo_files: RepoFiles | None = None,
) -> ValidationResult:
    """Deterministic gate for the deployment architecture submission.

    Confirms the description meets the configured minimum length and that the
    deploy script exists in the learner's fork before handing the real
    judgement to the LLM rubric grader. Missing script or repo yields an
    actionable failure; GitHub failures leave verification incomplete.
    """
    cfg = _deployment_architecture_config(requirement)
    if cfg is None or target is None:
        record_evidence_decision("evidence.configuration")
        return ValidationResult(
            is_valid=False,
            message=(
                "Requirement configuration error: missing deployment "
                "architecture config or required_repo."
            ),
            verification_completed=False,
            error_code="evidence.configuration",
        )

    min_length: int = getattr(cfg, "min_answer_length", 200)
    deploy_script_path: str = getattr(cfg, "deploy_script_path", "deploy.sh")
    try:
        deployment_architecture_task(
            DEPLOYMENT_ARCHITECTURE_RUBRIC_TASK,
            deploy_script_path,
        )
    except EvidenceError as exc:
        record_evidence_decision(exc.code)
        return exc.to_validation_result()

    stripped = description.strip()
    if len(stripped) < min_length:
        return ValidationResult(
            is_valid=False,
            message=(
                f"Your architecture description is too short. Write at least "
                f"{min_length} characters describing your deployment."
            ),
            verification_completed=True,
        )

    repo_files = repo_files or default_repo_files()
    try:
        file_paths = await repo_files.tree(target.owner, target.repo)
    except EvidenceError as exc:
        record_evidence_decision(exc.code)
        return exc.to_validation_result()
    except (GitHubServerError, httpx.HTTPStatusError, httpx.RequestError) as exc:
        record_evidence_decision("retrieval")
        if isinstance(exc, httpx.HTTPStatusError) and exc.response.status_code == 404:
            return ValidationResult(
                is_valid=False,
                message=(
                    f"Repository '{target.owner}/{target.repo}' not found. Make "
                    "sure you forked it and the fork is public."
                ),
                verification_completed=True,
                repo_exists=False,
            )
        return github_error_to_result(
            exc, event="deployment_architecture.repo_tree_error"
        )

    if deploy_script_path not in file_paths:
        record_evidence_decision("evidence.required_missing")
        other_scripts = _top_level_shell_scripts(file_paths)
        if other_scripts:
            found = ", ".join(other_scripts)
            hint = (
                f" Found {found}, but this check grades '{deploy_script_path}'. "
                f"Rename or add '{deploy_script_path}' at the repository root."
            )
        else:
            hint = (
                f" Add an idempotent '{deploy_script_path}' at the repository "
                "root that provisions your deployment."
            )
        return ValidationResult(
            is_valid=False,
            message=f"Could not find '{deploy_script_path}' in your repository.{hint}",
            verification_completed=True,
            error_code="evidence.required_missing",
        )

    return ValidationResult(
        is_valid=True,
        message="Description received and deploy script found. Reviewing alignment.",
    )


async def collect_deployment_architecture_evidence(
    owner: str,
    repo: str,
    description: str,
    task: VerificationTask = DEPLOYMENT_ARCHITECTURE_RUBRIC_TASK,
    deploy_script_path: str = "deploy.sh",
    repo_files: RepoFiles | None = None,
) -> EvidenceBundle:
    """Bundle the deploy script and the architecture description for grading."""
    repo_files = repo_files or default_repo_files()
    task = deployment_architecture_task(task, deploy_script_path)
    try:
        if task.evidence.max_files < 2:
            raise EvidenceError("evidence.file_limit")
        inventory = await repo_files.tree(owner, repo)
        if deploy_script_path not in inventory:
            raise EvidenceError(
                "evidence.required_missing", missing=[deploy_script_path]
            )
        script_content = await repo_files.file(owner, repo, deploy_script_path)
        if script_content is None:
            raise EvidenceError("evidence.changed")
    except (
        EvidenceError,
        GitHubServerError,
        httpx.HTTPStatusError,
        httpx.RequestError,
    ) as exc:
        record_evidence_decision(
            exc.code if isinstance(exc, EvidenceError) else "retrieval",
            selected_count=2,
        )
        if isinstance(exc, EvidenceError):
            exc.recorded = True
        raise
    return apply_evidence_cap(
        task,
        [
            (deploy_script_path, script_content),
            (_DESCRIPTION_EVIDENCE_PATH, description),
        ],
    )


def deployment_architecture_task(
    task: VerificationTask,
    deploy_script_path: str,
) -> VerificationTask:
    """Resolve the configured script without broadening the evidence contract."""
    required = task.evidence.required_files
    if (
        required
        not in (
            ["deploy.sh", _DESCRIPTION_EVIDENCE_PATH],
            [deploy_script_path, _DESCRIPTION_EVIDENCE_PATH],
        )
        or task.evidence.source != "repo_files"
    ):
        raise EvidenceError("evidence.configuration")
    policy = task.evidence.model_copy(
        update={
            "required_files": [deploy_script_path, _DESCRIPTION_EVIDENCE_PATH],
            "criterion_evidence": {
                criterion: [deploy_script_path, _DESCRIPTION_EVIDENCE_PATH]
                for criterion in task.evidence.criterion_evidence
            },
        }
    )
    validate_evidence_policy(policy)
    return task.model_copy(update={"evidence": policy})
