"""Unit tests for devops_verification_service.

Tests cover:
- Repository file tree filtering
- Prompt construction
- LLM response parsing (service-specific wrapper)
- Task result building (service-specific wrapper)
- End-to-end analyze_devops_repository flow

Shared utility tests (URL parsing, feedback sanitization, generic parsing)
live in test_llm_verification_base.py.
"""

import json
from unittest.mock import MagicMock, patch

import httpx
import pytest

from schemas import TaskResult, ValidationResult
from services.verification.devops_analysis import (
    DevOpsAnalysisError,
    _build_task_instructions,
    _build_task_prompt,
    _check_required_files,
    _filter_devops_files,
    analyze_devops_repository,
)
from services.verification.llm_base import build_task_results, parse_structured_response
from services.verification.tasks.phase5 import (
    MAX_FILES_PER_CATEGORY,
    PHASE5_TASKS,
    DevOpsTaskGrade,
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
            assert result[task["id"]] == []

    def test_no_devops_files(self):
        files = ["README.md", "api/main.py", "requirements.txt"]
        result = _filter_devops_files(files)
        for task in PHASE5_TASKS:
            assert result[task["id"]] == []

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
class TestParseStructuredResponse:
    """Tests for structured response parsing (single DevOpsTaskGrade per agent)."""

    def test_valid_response_from_value(self):
        """Should extract response from result.value."""
        expected = DevOpsTaskGrade(task_id="dockerfile", passed=True, feedback="Good")
        mock_result = MagicMock()
        mock_result.value = expected
        mock_result.text = ""

        result = parse_structured_response(
            mock_result,
            DevOpsTaskGrade,
            DevOpsAnalysisError,
            "devops_analysis.dockerfile",
        )
        assert result.task_id == "dockerfile"
        assert result.passed is True

    def test_fallback_to_text_parsing(self):
        """Should fall back to parsing result.text when value is None."""
        mock_result = MagicMock()
        mock_result.value = None
        mock_result.text = json.dumps(
            {"task_id": "dockerfile", "passed": True, "feedback": "Good"}
        )

        result = parse_structured_response(
            mock_result,
            DevOpsTaskGrade,
            DevOpsAnalysisError,
            "devops_analysis.dockerfile",
        )
        assert result.task_id == "dockerfile"

    def test_empty_text_raises(self):
        """Should raise when both value and text are empty."""
        mock_result = MagicMock()
        mock_result.value = None
        mock_result.text = ""

        with pytest.raises(DevOpsAnalysisError, match="No response received"):
            parse_structured_response(
                mock_result,
                DevOpsTaskGrade,
                DevOpsAnalysisError,
                "devops_analysis.dockerfile",
            )

    def test_invalid_text_raises(self):
        """Should raise when text is not valid JSON."""
        mock_result = MagicMock()
        mock_result.value = None
        mock_result.text = "This is just plain text with no JSON"

        with pytest.raises(DevOpsAnalysisError, match="Could not parse"):
            parse_structured_response(
                mock_result,
                DevOpsTaskGrade,
                DevOpsAnalysisError,
                "devops_analysis.dockerfile",
            )


@pytest.mark.unit
class TestBuildTaskResults:
    """Tests for converting parsed tasks to TaskResult objects."""

    def test_all_passed(self):
        grades = [
            DevOpsTaskGrade(task_id="dockerfile", passed=True, feedback="Done"),
            DevOpsTaskGrade(task_id="cicd-pipeline", passed=True, feedback="Done"),
            DevOpsTaskGrade(task_id="terraform-iac", passed=True, feedback="Done"),
            DevOpsTaskGrade(
                task_id="kubernetes-manifests", passed=True, feedback="Done"
            ),
        ]
        results, all_passed = build_task_results(grades, PHASE5_TASKS)
        assert all_passed is True
        assert len(results) == 4

    def test_some_failed(self):
        grades = [
            DevOpsTaskGrade(task_id="dockerfile", passed=True, feedback="Done"),
            DevOpsTaskGrade(task_id="cicd-pipeline", passed=False, feedback="Missing"),
            DevOpsTaskGrade(task_id="terraform-iac", passed=True, feedback="Done"),
            DevOpsTaskGrade(
                task_id="kubernetes-manifests",
                passed=False,
                feedback="Missing",
            ),
        ]
        results, all_passed = build_task_results(grades, PHASE5_TASKS)
        assert all_passed is False
        assert sum(1 for r in results if r.passed) == 2

    def test_missing_tasks_are_failed(self):
        """Tasks not in the response should be marked as failed."""
        grades = [
            DevOpsTaskGrade(task_id="dockerfile", passed=True, feedback="Done"),
            DevOpsTaskGrade(task_id="dockerfile", passed=True, feedback="Done"),
            DevOpsTaskGrade(task_id="dockerfile", passed=True, feedback="Done"),
            DevOpsTaskGrade(task_id="dockerfile", passed=True, feedback="Done"),
        ]
        results, all_passed = build_task_results(grades, PHASE5_TASKS)
        assert all_passed is False
        # dockerfile (4x) + 3 missing tasks filled in
        assert len(results) == 7
        failed = [r for r in results if not r.passed]
        assert len(failed) == 3

    def test_feedback_sanitized(self):
        grades = [
            DevOpsTaskGrade(
                task_id="dockerfile",
                passed=True,
                feedback="Visit <script>evil</script>",
            ),
            DevOpsTaskGrade(task_id="cicd-pipeline", passed=True, feedback="Done"),
            DevOpsTaskGrade(task_id="terraform-iac", passed=True, feedback="Done"),
            DevOpsTaskGrade(
                task_id="kubernetes-manifests", passed=True, feedback="Done"
            ),
        ]
        results, _ = build_task_results(grades, PHASE5_TASKS)
        dockerfile_result = next(
            r for r in results if r.task_name == "Containerization (Dockerfile)"
        )
        assert "<script>" not in dockerfile_result.feedback


@pytest.mark.unit
class TestBuildTaskPrompt:
    """Tests for per-task prompt and instructions construction."""

    def test_instructions_include_task_criteria(self):
        task_def = PHASE5_TASKS[0]  # dockerfile
        instructions = _build_task_instructions(task_def)
        for criterion in task_def["criteria"]:
            assert criterion in instructions

    def test_instructions_include_security_notice(self):
        task_def = PHASE5_TASKS[0]
        instructions = _build_task_instructions(task_def)
        assert "SECURITY NOTICE" in instructions

    def test_instructions_include_pass_indicators(self):
        task_def = PHASE5_TASKS[0]
        instructions = _build_task_instructions(task_def)
        assert "FROM " in instructions

    def test_prompt_includes_task_id(self):
        task_def = PHASE5_TASKS[0]
        prompt = _build_task_prompt(task_def, [])
        assert task_def["id"] in prompt

    def test_prompt_includes_file_contents(self):
        task_def = PHASE5_TASKS[0]
        dockerfile = (
            '<file_content path="Dockerfile">\nFROM python:3.12\n</file_content>'
        )
        prompt = _build_task_prompt(task_def, [dockerfile])
        assert "FROM python:3.12" in prompt

    def test_prompt_marks_missing_files(self):
        task_def = PHASE5_TASKS[0]
        prompt = _build_task_prompt(task_def, [])
        assert "<no_files_found />" in prompt

    def test_each_task_gets_unique_instructions(self):
        """Each task's instructions should mention its own name."""
        for task_def in PHASE5_TASKS:
            instructions = _build_task_instructions(task_def)
            assert task_def["name"] in instructions


@pytest.mark.unit
class TestAnalyzeDevopsRepository:
    """Tests for the main entry point."""

    @pytest.mark.asyncio
    async def test_invalid_url(self):
        result = await analyze_devops_repository("not-a-github-url", "testuser")
        assert result.is_valid is False
        assert "Invalid GitHub repository URL" in result.message

    @pytest.mark.asyncio
    async def test_username_mismatch(self):
        result = await analyze_devops_repository(
            "https://github.com/otheruser/journal-starter",
            "testuser",
        )
        assert result.is_valid is False
        assert "does not match" in result.message
        assert result.username_match is False

    @pytest.mark.asyncio
    async def test_repo_not_found(self):
        """Should return clear error when repository doesn't exist."""
        mock_response = MagicMock()
        mock_response.status_code = 404

        with (
            patch(
                "services.verification.devops_analysis.get_llm_chat_client",
                autospec=True,
            ),
            patch(
                "services.verification.devops_analysis.fetch_repo_tree",
                autospec=True,
                side_effect=httpx.HTTPStatusError(
                    "Not Found", request=MagicMock(), response=mock_response
                ),
            ),
        ):
            result = await analyze_devops_repository(
                "https://github.com/testuser/journal-starter",
                "testuser",
            )

        assert result.is_valid is False
        assert "not found" in result.message.lower()

    @pytest.mark.asyncio
    async def test_successful_analysis_all_pass(self):
        """Full flow with all tasks passing."""
        mock_validation = ValidationResult(
            is_valid=True,
            message="All 4 DevOps tasks verified!",
            task_results=[
                TaskResult(
                    task_name=t["name"],
                    passed=True,
                    feedback="Well done!",
                )
                for t in PHASE5_TASKS
            ],
        )

        with patch(
            "services.verification.devops_analysis._run_devops_workflow",
            autospec=True,
            return_value=mock_validation,
        ):
            result = await analyze_devops_repository(
                "https://github.com/testuser/journal-starter",
                "testuser",
            )

        assert result.is_valid is True

    @pytest.mark.asyncio
    async def test_all_missing_skips_llm(self):
        """When no tasks pass existence check, skip LLM and return fast."""
        with (
            patch(
                "services.verification.devops_analysis.get_llm_chat_client",
                autospec=True,
            ),
            patch(
                "services.verification.devops_analysis.fetch_repo_tree",
                autospec=True,
                return_value=["README.md"],
            ),
        ):
            result = await analyze_devops_repository(
                "https://github.com/testuser/journal-starter",
                "testuser",
            )

        assert result.is_valid is False
        assert result.task_results is not None
        assert len(result.task_results) == 4
        assert all(not t.passed for t in result.task_results)

    @pytest.mark.asyncio
    async def test_partial_missing_fails_immediately(self):
        """If any task is missing required files, fail immediately
        without calling the LLM."""
        mock_files = [
            "Dockerfile",
            ".github/workflows/ci.yml",
            "infra/main.tf",
            "k8s/deployment.yaml",
            # k8s/service.yaml intentionally absent
        ]

        with (
            patch(
                "services.verification.devops_analysis.get_llm_chat_client",
                autospec=True,
            ),
            patch(
                "services.verification.devops_analysis.fetch_repo_tree",
                autospec=True,
                return_value=mock_files,
            ),
        ):
            result = await analyze_devops_repository(
                "https://github.com/testuser/journal-starter",
                "testuser",
            )

        assert result.is_valid is False
        assert result.task_results is not None
        assert len(result.task_results) == 1
        k8s_result = result.task_results[0]
        assert "Kubernetes" in k8s_result.task_name
        assert "k8s/service.yaml" in k8s_result.feedback

    @pytest.mark.asyncio
    async def test_llm_client_error_propagates(self):
        """LLMClientError should propagate to the dispatcher."""
        from core.llm_client import LLMClientError

        with (
            patch(
                "services.verification.devops_analysis._run_devops_workflow",
                autospec=True,
                side_effect=LLMClientError("Connection failed", retriable=True),
            ),
            pytest.raises(LLMClientError, match="Connection failed"),
        ):
            await analyze_devops_repository(
                "https://github.com/testuser/journal-starter",
                "testuser",
            )

    @pytest.mark.asyncio
    async def test_devops_analysis_error_propagates(self):
        """DevOpsAnalysisError should propagate to the dispatcher."""
        with (
            patch(
                "services.verification.devops_analysis._run_devops_workflow",
                autospec=True,
                side_effect=DevOpsAnalysisError("Timeout", retriable=True),
            ),
            pytest.raises(DevOpsAnalysisError, match="Timeout"),
        ):
            await analyze_devops_repository(
                "https://github.com/testuser/journal-starter",
                "testuser",
            )
