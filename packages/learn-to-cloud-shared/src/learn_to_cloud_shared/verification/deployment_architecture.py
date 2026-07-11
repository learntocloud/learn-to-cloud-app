"""Phase 4 capstone deployment-architecture verification.

Hybrid of Phase 7 (free-text + LLM rubric) and Phase 3 (repo-file evidence):
the learner writes an architecture description in the app, and the grader
fetches ``deploy.sh`` from their fork of the required repo. The deterministic
stage confirms the description meets a minimum length and that the deploy
script exists in the repo tree; the LLM rubric then judges whether the
description aligns with what the script actually provisions.
"""

from __future__ import annotations

from hashlib import sha256

import httpx

from learn_to_cloud_shared.github_target import GitHubTarget
from learn_to_cloud_shared.schemas import HandsOnRequirement, ValidationResult
from learn_to_cloud_shared.verification.evidence import truncate_to_bytes
from learn_to_cloud_shared.verification.repo_files import RepoFiles, default_repo_files
from learn_to_cloud_shared.verification.tasks.base import (
    EvidenceBundle,
    EvidenceItem,
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
    target: GitHubTarget | None,
    repo_files: RepoFiles | None = None,
) -> ValidationResult:
    """Deterministic gate for the deployment architecture submission.

    Confirms the description meets the configured minimum length and that the
    deploy script exists in the learner's fork before handing the real
    judgement to the LLM rubric grader. Missing script or repo yields an
    actionable failure; transient GitHub errors bubble up so the engine
    records them as operational failures.
    """
    cfg = _deployment_architecture_config(requirement)
    if cfg is None or target is None or not target.repo:
        return ValidationResult(
            is_valid=False,
            message=(
                "Requirement configuration error: missing deployment "
                "architecture config or required_repo."
            ),
            verification_completed=True,
        )

    min_length: int = getattr(cfg, "min_answer_length", 200)
    deploy_script_path: str = getattr(cfg, "deploy_script_path", "deploy.sh")

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
    except httpx.HTTPStatusError as exc:
        if exc.response.status_code == 404:
            return ValidationResult(
                is_valid=False,
                message=(
                    f"Repository '{target.owner}/{target.repo}' not found. Make "
                    "sure you forked it and the fork is public."
                ),
                verification_completed=True,
                repo_exists=False,
            )
        raise

    if deploy_script_path not in file_paths:
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
    items: list[EvidenceItem] = []
    total_bytes = 0

    script_content = await repo_files.file(owner, repo, deploy_script_path)
    if script_content is not None:
        items.append(
            _bounded_item(
                deploy_script_path, script_content, task.evidence.max_file_size_bytes
            )
        )
        total_bytes += len(items[-1].content.encode("utf-8"))

    description_item = _bounded_item(
        _DESCRIPTION_EVIDENCE_PATH, description, task.evidence.max_file_size_bytes
    )
    items.append(description_item)
    total_bytes += len(description_item.content.encode("utf-8"))

    return EvidenceBundle(
        task_id=task.id,
        source=task.evidence.source,
        items=items,
        total_bytes=total_bytes,
    )


def _bounded_item(path: str, content: str, max_bytes: int) -> EvidenceItem:
    encoded = content.encode("utf-8")
    truncated = False
    if len(encoded) > max_bytes:
        content = truncate_to_bytes(content, max_bytes)
        encoded = content.encode("utf-8")
        truncated = True
    return EvidenceItem(
        path=path,
        content=content,
        sha256=sha256(encoded).hexdigest(),
        truncated=truncated,
    )
