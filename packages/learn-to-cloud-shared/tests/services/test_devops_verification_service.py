"""Unit tests for devops_verification_service.

Tests cover:
- Repository file tree filtering
- Required file existence checks
- Deterministic indicator checking per task
- End-to-end run_devops_workflow flow
"""

from unittest.mock import MagicMock, patch

import httpx
import pytest

from learn_to_cloud_shared.verification.devops_analysis import (
    _check_required_files,
    _check_task_indicators,
    _filter_devops_files,
    run_devops_workflow,
)
from learn_to_cloud_shared.verification.tasks.base import (
    EvidencePolicy,
    IndicatorGraderConfig,
    VerificationTask,
)
from learn_to_cloud_shared.verification.tasks.phase5 import (
    MAX_FILES_PER_CATEGORY,
    PHASE5_TASKS,
)


@pytest.mark.unit
class TestFilterDevopsFiles:
    """Tests for file tree filtering logic."""

    def test_finds_dockerfile(self):
        files = ["README.md", "Dockerfile", "api/main.py"]
        result = _filter_devops_files(files)
        assert result["dockerfile"] == ["Dockerfile"]

    def test_finds_lowercase_dockerfile(self):
        files = ["readme.md", "dockerfile", "api/main.py"]
        result = _filter_devops_files(files)
        assert result["dockerfile"] == ["dockerfile"]

    def test_finds_github_workflows(self):
        files = [
            ".github/workflows/ci.yml",
            ".github/workflows/deploy.yml",
            ".github/CODEOWNERS",
        ]
        result = _filter_devops_files(files)
        assert len(result["cicd-pipeline"]) == 2
        assert ".github/workflows/ci.yml" in result["cicd-pipeline"]

    def test_finds_terraform_files(self):
        files = ["infra/main.tf", "infra/variables.tf", "infra/outputs.tf"]
        result = _filter_devops_files(files)
        assert len(result["terraform-iac"]) == 3

    def test_finds_kubernetes_files(self):
        files = ["k8s/deployment.yaml", "k8s/service.yaml"]
        result = _filter_devops_files(files)
        assert len(result["kubernetes-manifests"]) == 2

    def test_empty_repo(self):
        result = _filter_devops_files([])
        for task in PHASE5_TASKS:
            assert result[task.id] == []

    def test_no_devops_files(self):
        files = ["README.md", "api/main.py", "requirements.txt"]
        result = _filter_devops_files(files)
        for task in PHASE5_TASKS:
            assert result[task.id] == []

    def test_limits_files_per_category(self):
        """Should cap files per category to MAX_FILES_PER_CATEGORY."""
        files = [f"infra/file{i}.tf" for i in range(20)]
        result = _filter_devops_files(files)
        assert len(result["terraform-iac"]) == 10  # MAX_FILES_PER_CATEGORY

    def test_exact_match_files_prioritized_over_directory_matches(self):
        """Exact-match patterns (e.g. k8s/service.yaml) must be included
        even when subdirectory files (e.g. k8s/monitoring/*) would fill
        the per-category cap first."""
        monitoring_files = [f"k8s/monitoring/file{i}.yaml" for i in range(15)]
        files = monitoring_files + [
            "k8s/deployment.yaml",
            "k8s/service.yaml",
            "k8s/secrets.yaml.example",
        ]
        result = _filter_devops_files(files)
        k8s = result["kubernetes-manifests"]
        assert len(k8s) == MAX_FILES_PER_CATEGORY
        # Critical files always present regardless of alphabetical order
        assert "k8s/deployment.yaml" in k8s
        assert "k8s/service.yaml" in k8s
        assert "k8s/secrets.yaml.example" in k8s


@pytest.mark.unit
class TestCheckFileExistence:
    """Tests for the static existence pre-check."""

    def test_all_files_present(self):
        """All tasks pass when required files and directory prefixes exist."""
        all_files = [
            "Dockerfile",
            ".dockerignore",
            ".github/workflows/ci.yml",
            "infra/main.tf",
            "k8s/deployment.yaml",
            "k8s/service.yaml",
        ]
        failures = _check_required_files(all_files)
        assert len(failures) == 0

    def test_missing_required_file_fails_task(self):
        """Task fails when a required_file is missing from the full tree."""
        all_files = [
            "Dockerfile",
            ".github/workflows/ci.yml",
            "infra/main.tf",
            "k8s/deployment.yaml",
            # k8s/service.yaml is missing
        ]
        failures = _check_required_files(all_files)
        k8s_failure = next(f for f in failures if "Kubernetes" in f.task_name)
        assert not k8s_failure.passed
        assert "k8s/service.yaml" in k8s_failure.feedback

    def test_missing_dockerfile_fails_task(self):
        """Dockerfile task fails when Dockerfile is not in the tree."""
        all_files = [
            ".github/workflows/ci.yml",
            "infra/main.tf",
            "k8s/deployment.yaml",
            "k8s/service.yaml",
        ]
        failures = _check_required_files(all_files)
        docker_failure = next(f for f in failures if "Dockerfile" in f.task_name)
        assert "Dockerfile" in docker_failure.feedback

    def test_no_files_at_all_fails_everything(self):
        """All tasks fail for a completely empty repository."""
        failures = _check_required_files([])
        assert len(failures) == 4

    def test_missing_directory_prefix_fails_task(self):
        """Tasks with directory prefix requirements fail when no
        files exist under that directory."""
        all_files = [
            "Dockerfile",
            "k8s/deployment.yaml",
            "k8s/service.yaml",
            # No .github/workflows/ or infra/ files
        ]
        failures = _check_required_files(all_files)
        assert len(failures) == 2
        cicd_failure = next(f for f in failures if "CI/CD" in f.task_name)
        assert ".github/workflows/" in cicd_failure.feedback

    def test_required_files_checked_against_full_tree(self):
        """required_files are checked against the full tree, not the
        filtered subset -- defense-in-depth against filter bugs."""
        all_files = [
            "Dockerfile",
            ".github/workflows/ci.yml",
            "infra/main.tf",
            "k8s/deployment.yaml",
            "k8s/service.yaml",
        ] + [f"k8s/monitoring/file{i}.yaml" for i in range(20)]
        failures = _check_required_files(all_files)
        assert len(failures) == 0


@pytest.mark.unit
class TestCheckTaskIndicators:
    """Tests for deterministic indicator checking."""

    def test_all_indicators_matched_passes(self):
        """Task passes when enough indicators are found."""
        task_def = PHASE5_TASKS[0]  # Dockerfile
        contents = [
            "FROM python:3.12-slim\n"
            "WORKDIR /app\n"
            "COPY requirements.txt .\n"
            "RUN pip install -r requirements.txt\n"
            "COPY . .\n"
            "EXPOSE 8000\n"
            'CMD ["uvicorn", "learn_to_cloud.main:app"]\n'
        ]
        result = _check_task_indicators(task_def, contents)
        assert result.passed is True

    def test_too_few_indicators_fails(self):
        """Task fails when matched count < min_pass_count."""
        task_def = PHASE5_TASKS[0]  # Dockerfile, min_pass_count=5
        contents = ["FROM python:3.12\nWORKDIR /app\n"]  # only 2 indicators
        result = _check_task_indicators(task_def, contents)
        assert result.passed is False
        assert "Missing:" in result.feedback

    def test_fail_indicator_causes_failure(self):
        """Any fail_indicator match → immediate failure."""
        # Use a synthetic task_def since real Phase 5 tasks may not have fail_indicators
        task_def = VerificationTask(
            id="test-task",
            phase_id=5,
            name="Test Task",
            evidence=EvidencePolicy(source="repo_files"),
            grader=IndicatorGraderConfig(
                pass_indicators=["FROM "],
                fail_indicators=["TODO"],
                min_pass_count=1,
            ),
        )
        contents = ["FROM python:3.12\nTODO: fix this\n"]
        result = _check_task_indicators(task_def, contents)
        assert result.passed is False
        assert "disallowed" in result.feedback.lower()

    def test_empty_files_fails(self):
        """No file content → fails (insufficient indicators)."""
        task_def = PHASE5_TASKS[0]
        result = _check_task_indicators(task_def, [])
        assert result.passed is False

    def test_case_insensitive_matching(self):
        """Indicator matching is case-insensitive."""
        task_def = PHASE5_TASKS[0]  # Dockerfile
        contents = [
            "from python:3.12\n"
            "workdir /app\n"
            "copy . .\n"
            "run pip install\n"
            "expose 8000\n"
            "cmd uvicorn\n"
        ]
        result = _check_task_indicators(task_def, contents)
        assert result.passed is True

    def test_cicd_task_indicators(self):
        """CI/CD pipeline task passes with enough workflow indicators."""
        task_def = next(t for t in PHASE5_TASKS if t.id == "cicd-pipeline")
        contents = [
            "name: CI\n"
            "on:\n  push:\n    branches: [main]\n"
            "jobs:\n  build:\n"
            "    runs-on: ubuntu-latest\n"
            "    steps:\n"
            "      - uses: actions/checkout@v4\n"
            "      - run: pytest\n"
        ]
        result = _check_task_indicators(task_def, contents)
        assert result.passed is True

    def test_terraform_task_indicators(self):
        """Terraform task passes with enough IaC indicators."""
        task_def = next(t for t in PHASE5_TASKS if t.id == "terraform-iac")
        contents = [
            'resource "azurerm_resource_group" "rg" {\n'
            '  name     = "myapp"\n'
            '  location = "eastus"\n'
            "}\n\n"
            'variable "location" {\n'
            '  default = "eastus"\n'
            "}\n\n"
            'output "rg_id" {\n'
            "  value = azurerm_resource_group.rg.id\n"
            "}\n\n"
            'provider "azurerm" {\n'
            "  features {}\n"
            "}\n"
        ]
        result = _check_task_indicators(task_def, contents)
        assert result.passed is True


@pytest.mark.unit
class TestRunDevopsWorkflow:
    """Tests for the DevOps workflow execution."""

    @pytest.mark.asyncio
    async def test_repo_not_found(self):
        """Should return clear error when repository doesn't exist."""
        mock_response = MagicMock()
        mock_response.status_code = 404

        with patch(
            "learn_to_cloud_shared.verification.devops_analysis.fetch_repo_tree",
            autospec=True,
            side_effect=httpx.HTTPStatusError(
                "Not Found", request=MagicMock(), response=mock_response
            ),
        ):
            result = await run_devops_workflow("testuser", "journal-starter")

        assert result.is_valid is False
        assert "not found" in result.message.lower()

    @pytest.mark.asyncio
    async def test_all_missing_returns_fast(self):
        """When no tasks pass existence check, return immediately."""
        with patch(
            "learn_to_cloud_shared.verification.devops_analysis.fetch_repo_tree",
            autospec=True,
            return_value=["README.md"],
        ):
            result = await run_devops_workflow("testuser", "journal-starter")

        assert result.is_valid is False
        assert result.task_results is not None
        assert len(result.task_results) == 4
        assert all(not t.passed for t in result.task_results)

    @pytest.mark.asyncio
    async def test_partial_missing_fails_immediately(self):
        """If any task is missing required files, fail immediately."""
        mock_files = [
            "Dockerfile",
            ".github/workflows/ci.yml",
            "infra/main.tf",
            "k8s/deployment.yaml",
            # k8s/service.yaml intentionally absent
        ]

        with patch(
            "learn_to_cloud_shared.verification.devops_analysis.fetch_repo_tree",
            autospec=True,
            return_value=mock_files,
        ):
            result = await run_devops_workflow("testuser", "journal-starter")

        assert result.is_valid is False
        assert result.task_results is not None
        assert len(result.task_results) == 1
        k8s_result = result.task_results[0]
        assert "Kubernetes" in k8s_result.task_name
        assert "k8s/service.yaml" in k8s_result.feedback

    @pytest.mark.asyncio
    async def test_all_tasks_pass_with_good_content(self):
        """Happy path: all required files exist with proper content."""
        mock_files = [
            "Dockerfile",
            ".dockerignore",
            ".github/workflows/ci.yml",
            "infra/main.tf",
            "infra/variables.tf",
            "k8s/deployment.yaml",
            "k8s/service.yaml",
        ]

        dockerfile_content = (
            "FROM python:3.12-slim\nWORKDIR /app\n"
            "COPY requirements.txt .\nRUN pip install -r requirements.txt\n"
            'COPY . .\nEXPOSE 8000\nCMD ["uvicorn", "learn_to_cloud.main:app"]\n'
        )
        cicd_content = (
            "name: CI\non:\n  push:\n    branches: [main]\n"
            "jobs:\n  build:\n    runs-on: ubuntu-latest\n"
            "    steps:\n      - uses: actions/checkout@v4\n"
            "      - run: pytest\n"
        )
        terraform_content = (
            'resource "azurerm_resource_group" "rg" {\n'
            '  name = "myapp"\n  location = "eastus"\n}\n'
            'variable "location" {\n  default = "eastus"\n}\n'
            'output "rg_id" {\n  value = azurerm_resource_group.rg.id\n}\n'
            'provider "azurerm" {\n  features {}\n}\n'
        )
        k8s_deploy_content = (
            "apiVersion: apps/v1\nkind: Deployment\nmetadata:\n"
            "  name: journal\nspec:\n  replicas: 1\n"
            "  selector:\n    matchLabels:\n      app: journal\n"
            "  template:\n    spec:\n      containers:\n"
            "        - name: journal\n          image: IMAGE_PLACEHOLDER\n"
            "          ports:\n            - containerPort: 8000\n"
            "          envFrom:\n            - secretRef:\n"
            "                name: journal-secrets\n"
            "          livenessProbe:\n            httpGet:\n"
            "              path: /health\n              port: 8000\n"
            "          readinessProbe:\n            httpGet:\n"
            "              path: /health\n              port: 8000\n"
        )

        file_map = {
            "Dockerfile": dockerfile_content,
            ".dockerignore": "*.pyc\n__pycache__\n",
            ".github/workflows/ci.yml": cicd_content,
            "infra/main.tf": terraform_content,
            "infra/variables.tf": 'variable "x" {}\n',
            "k8s/deployment.yaml": k8s_deploy_content,
            "k8s/service.yaml": (
                "apiVersion: v1\nkind: Service\nmetadata:\n"
                "  name: journal\nspec:\n  ports:\n"
                "    - port: 80\n      targetPort: 8000\n"
            ),
        }

        async def mock_fetch(owner, repo, path, branch="main"):
            return file_map.get(path, "")

        with (
            patch(
                "learn_to_cloud_shared.verification.devops_analysis.fetch_repo_tree",
                autospec=True,
                return_value=mock_files,
            ),
            patch(
                "learn_to_cloud_shared.verification.devops_analysis._fetch_file_content",
                side_effect=mock_fetch,
            ),
        ):
            result = await run_devops_workflow("testuser", "journal-starter")

        assert result.is_valid is True
        assert result.task_results is not None
        assert len(result.task_results) == 4
        assert all(t.passed for t in result.task_results)
