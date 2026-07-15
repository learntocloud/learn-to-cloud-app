"""Tests for the deterministic Phase 5 repository gate."""

import httpx
import pytest

from learn_to_cloud_shared.verification.devops_analysis import (
    check_required_devops_files,
    missing_required_devops_paths,
    select_devops_evidence_paths,
    verify_required_devops_files,
)
from learn_to_cloud_shared.verification.repo_files import InMemoryRepoFiles


def _complete_tree() -> list[str]:
    return [
        "Dockerfile",
        ".dockerignore",
        ".github/workflows/deploy.yml",
        "infra/main.tf",
        "infra/variables.tf",
        "k8s/deployment.yaml",
        "k8s/service.yaml",
        "k8s/secrets.yaml.example",
    ]


@pytest.mark.unit
def test_required_files_pass_when_all_prescribed_paths_exist():
    result = check_required_devops_files(_complete_tree())

    assert result.is_valid is True
    assert result.task_results is not None
    assert result.task_results[0].task_name == "Required DevOps Files"
    assert result.task_results[0].passed is True


@pytest.mark.unit
def test_required_files_report_every_missing_path():
    result = check_required_devops_files(["Dockerfile", "k8s/deployment.yaml"])

    assert result.is_valid is False
    assert result.task_results is not None
    feedback = result.task_results[0].feedback
    assert ".github/workflows/" in feedback
    assert "infra/" in feedback
    assert "k8s/service.yaml" in feedback


@pytest.mark.unit
def test_required_paths_are_case_insensitive():
    files = [
        "dockerfile",
        ".GITHUB/WORKFLOWS/CI.YML",
        "INFRA/MAIN.TF",
        "K8S/DEPLOYMENT.YAML",
        "K8S/SERVICE.YAML",
    ]

    assert missing_required_devops_paths(files) == []


@pytest.mark.unit
def test_evidence_selection_prioritizes_exact_critical_files():
    files = [
        *[f".github/workflows/generated-{index}.yml" for index in range(20)],
        *[f"infra/module-{index}.tf" for index in range(20)],
        "Dockerfile",
        ".dockerignore",
        "k8s/deployment.yaml",
        "k8s/service.yaml",
        "k8s/secrets.yaml.example",
    ]

    selected = select_devops_evidence_paths(files, max_files=8)

    assert selected[:5] == [
        "Dockerfile",
        ".dockerignore",
        "k8s/deployment.yaml",
        "k8s/service.yaml",
        "k8s/secrets.yaml.example",
    ]
    assert len(selected) == 8


@pytest.mark.unit
def test_evidence_selection_is_deterministic_and_deduplicated():
    files = [
        "infra/z.tf",
        "Dockerfile",
        "infra/a.tf",
        "k8s/deployment.yaml",
        "k8s/deployment.yaml",
    ]

    assert select_devops_evidence_paths(files) == [
        "Dockerfile",
        "k8s/deployment.yaml",
        "infra/a.tf",
        "infra/z.tf",
    ]


@pytest.mark.asyncio
async def test_repository_error_is_reported_as_incomplete_verification():
    response = httpx.Response(
        status_code=403,
        request=httpx.Request("GET", "https://api.github.com/repo"),
    )
    repo_files = InMemoryRepoFiles(
        tree_error=httpx.HTTPStatusError(
            "Forbidden",
            request=response.request,
            response=response,
        )
    )

    result = await verify_required_devops_files(
        "learner",
        "journal-starter",
        repo_files,
    )

    assert result.is_valid is False
    assert result.verification_completed is False
    assert "GitHub API error" in result.message
