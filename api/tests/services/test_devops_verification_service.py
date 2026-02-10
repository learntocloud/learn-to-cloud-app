"""Unit tests for devops_verification_service.

Tests cover:
- GitHub URL parsing and validation
- Repository file tree filtering
- Prompt construction
- LLM response parsing
- Feedback sanitization
- End-to-end analyze_devops_repository flow
"""

import json
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from schemas import TaskResult, ValidationResult
from services.devops_verification_service import (
    PHASE5_TASKS,
    DevOpsAnalysisError,
    DevOpsAnalysisLLMResponse,
    DevOpsTaskGrade,
    _build_task_results,
    _build_verification_prompt,
    _extract_repo_info,
    _filter_devops_files,
    _parse_structured_response,
    _sanitize_feedback,
    analyze_devops_repository,
)


@pytest.mark.unit
class TestExtractRepoInfo:
    """Tests for GitHub URL parsing."""

    def test_standard_url(self):
        owner, repo = _extract_repo_info("https://github.com/testuser/journal-starter")
        assert owner == "testuser"
        assert repo == "journal-starter"

    def test_url_with_trailing_slash(self):
        owner, repo = _extract_repo_info("https://github.com/testuser/journal-starter/")
        assert owner == "testuser"
        assert repo == "journal-starter"

    def test_url_with_git_suffix(self):
        owner, repo = _extract_repo_info(
            "https://github.com/testuser/journal-starter.git"
        )
        assert owner == "testuser"
        assert repo == "journal-starter"

    def test_url_with_subpath(self):
        owner, repo = _extract_repo_info(
            "https://github.com/testuser/journal-starter/tree/main/infra"
        )
        assert owner == "testuser"
        assert repo == "journal-starter"

    def test_url_with_whitespace(self):
        owner, repo = _extract_repo_info(
            "  https://github.com/testuser/journal-starter  "
        )
        assert owner == "testuser"
        assert repo == "journal-starter"

    def test_invalid_url_raises(self):
        with pytest.raises(ValueError, match="Invalid GitHub repository URL"):
            _extract_repo_info("https://gitlab.com/testuser/repo")

    def test_empty_url_raises(self):
        with pytest.raises(ValueError, match="Invalid GitHub repository URL"):
            _extract_repo_info("")

    def test_non_url_raises(self):
        with pytest.raises(ValueError, match="Invalid GitHub repository URL"):
            _extract_repo_info("not-a-url")


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
        assert len(result["terraform-iac"]) == 5  # MAX_FILES_PER_CATEGORY


@pytest.mark.unit
class TestParseStructuredResponse:
    """Tests for structured response parsing."""

    def test_valid_response_from_value(self):
        """Should extract response from result.value."""
        expected = DevOpsAnalysisLLMResponse(
            tasks=[
                DevOpsTaskGrade(task_id="dockerfile", passed=True, feedback="Good"),
                DevOpsTaskGrade(task_id="cicd-pipeline", passed=True, feedback="Good"),
                DevOpsTaskGrade(task_id="terraform-iac", passed=True, feedback="Good"),
                DevOpsTaskGrade(
                    task_id="kubernetes-manifests", passed=True, feedback="Good"
                ),
            ]
        )
        mock_result = MagicMock()
        mock_result.value = expected
        mock_result.text = ""

        result = _parse_structured_response(mock_result)
        assert len(result.tasks) == 4
        assert result.tasks[0].task_id == "dockerfile"
        assert result.tasks[0].passed is True

    def test_fallback_to_text_parsing(self):
        """Should fall back to parsing result.text when value is None."""
        tasks = [
            {"task_id": t["id"], "passed": True, "feedback": "Good"}
            for t in PHASE5_TASKS
        ]
        mock_result = MagicMock()
        mock_result.value = None
        mock_result.text = json.dumps({"tasks": tasks})

        result = _parse_structured_response(mock_result)
        assert len(result.tasks) == 4

    def test_empty_text_raises(self):
        """Should raise when both value and text are empty."""
        mock_result = MagicMock()
        mock_result.value = None
        mock_result.text = ""

        with pytest.raises(DevOpsAnalysisError, match="No response received"):
            _parse_structured_response(mock_result)

    def test_invalid_text_raises(self):
        """Should raise when text is not valid JSON."""
        mock_result = MagicMock()
        mock_result.value = None
        mock_result.text = "This is just plain text with no JSON"

        with pytest.raises(DevOpsAnalysisError, match="Could not parse"):
            _parse_structured_response(mock_result)


@pytest.mark.unit
class TestSanitizeFeedback:
    """Tests for feedback sanitization."""

    def test_normal_feedback(self):
        assert _sanitize_feedback("Great job!") == "Great job!"

    def test_empty_feedback(self):
        assert _sanitize_feedback("") == "No feedback provided"

    def test_none_feedback(self):
        assert _sanitize_feedback(None) == "No feedback provided"

    def test_truncates_long_feedback(self):
        long = "x " * 500
        result = _sanitize_feedback(long)
        assert len(result) <= 503  # 500 + "..."

    def test_removes_html_tags(self):
        result = _sanitize_feedback("Good <script>alert('xss')</script> job!")
        assert "<script>" not in result
        assert "</script>" not in result

    def test_removes_urls(self):
        result = _sanitize_feedback("See https://malicious.com for details")
        assert "https://" not in result
        assert "[link removed]" in result

    def test_removes_code_blocks(self):
        result = _sanitize_feedback("Try ```\nmalicious code\n``` this")
        assert "malicious code" not in result


@pytest.mark.unit
class TestBuildTaskResults:
    """Tests for converting parsed tasks to TaskResult objects."""

    def test_all_passed(self):
        analysis = DevOpsAnalysisLLMResponse(
            tasks=[
                DevOpsTaskGrade(task_id="dockerfile", passed=True, feedback="Done"),
                DevOpsTaskGrade(task_id="cicd-pipeline", passed=True, feedback="Done"),
                DevOpsTaskGrade(task_id="terraform-iac", passed=True, feedback="Done"),
                DevOpsTaskGrade(
                    task_id="kubernetes-manifests", passed=True, feedback="Done"
                ),
            ]
        )
        results, all_passed = _build_task_results(analysis)
        assert all_passed is True
        assert len(results) == 4

    def test_some_failed(self):
        analysis = DevOpsAnalysisLLMResponse(
            tasks=[
                DevOpsTaskGrade(task_id="dockerfile", passed=True, feedback="Done"),
                DevOpsTaskGrade(
                    task_id="cicd-pipeline", passed=False, feedback="Missing"
                ),
                DevOpsTaskGrade(task_id="terraform-iac", passed=True, feedback="Done"),
                DevOpsTaskGrade(
                    task_id="kubernetes-manifests",
                    passed=False,
                    feedback="Missing",
                ),
            ]
        )
        results, all_passed = _build_task_results(analysis)
        assert all_passed is False
        assert sum(1 for r in results if r.passed) == 2

    def test_missing_tasks_are_failed(self):
        """Tasks not in the response should be marked as failed."""
        # With structured output enforcing min/max length=4, we test
        # the fallback by providing duplicate task_ids.
        analysis = DevOpsAnalysisLLMResponse(
            tasks=[
                DevOpsTaskGrade(task_id="dockerfile", passed=True, feedback="Done"),
                DevOpsTaskGrade(task_id="dockerfile", passed=True, feedback="Done"),
                DevOpsTaskGrade(task_id="dockerfile", passed=True, feedback="Done"),
                DevOpsTaskGrade(task_id="dockerfile", passed=True, feedback="Done"),
            ]
        )
        results, all_passed = _build_task_results(analysis)
        assert all_passed is False
        # dockerfile (4x) + 3 missing tasks filled in
        assert len(results) == 7
        failed = [r for r in results if not r.passed]
        assert len(failed) == 3

    def test_feedback_sanitized(self):
        analysis = DevOpsAnalysisLLMResponse(
            tasks=[
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
        )
        results, _ = _build_task_results(analysis)
        dockerfile_result = next(
            r for r in results if r.task_name == "Containerization (Dockerfile)"
        )
        assert "<script>" not in dockerfile_result.feedback


@pytest.mark.unit
class TestBuildVerificationPrompt:
    """Tests for prompt construction."""

    def test_includes_all_task_ids(self):
        file_contents = {t["id"]: [] for t in PHASE5_TASKS}
        prompt = _build_verification_prompt(
            "testuser", "journal-starter", file_contents
        )

        for task in PHASE5_TASKS:
            assert task["id"] in prompt

    def test_includes_file_contents(self):
        dockerfile = (
            '<file_content path="Dockerfile">' "\nFROM python:3.12\n</file_content>"
        )
        file_contents = {
            "dockerfile": [dockerfile],
            "cicd-pipeline": [],
            "terraform-iac": [],
            "kubernetes-manifests": [],
        }
        prompt = _build_verification_prompt(
            "testuser", "journal-starter", file_contents
        )
        assert "FROM python:3.12" in prompt

    def test_marks_missing_files(self):
        file_contents = {t["id"]: [] for t in PHASE5_TASKS}
        prompt = _build_verification_prompt(
            "testuser", "journal-starter", file_contents
        )
        assert "<no_files_found />" in prompt

    def test_includes_security_notice(self):
        file_contents = {t["id"]: [] for t in PHASE5_TASKS}
        prompt = _build_verification_prompt(
            "testuser", "journal-starter", file_contents
        )
        assert "SECURITY NOTICE" in prompt

    def test_includes_repo_info(self):
        file_contents = {t["id"]: [] for t in PHASE5_TASKS}
        prompt = _build_verification_prompt(
            "testuser", "journal-starter", file_contents
        )
        assert "testuser" in prompt
        assert "journal-starter" in prompt


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

        with patch(
            "services.devops_verification_service._fetch_repo_tree",
            new_callable=AsyncMock,
            side_effect=httpx.HTTPStatusError(
                "Not Found", request=MagicMock(), response=mock_response
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
        mock_files = [
            "Dockerfile",
            ".github/workflows/ci.yml",
            "infra/main.tf",
            "k8s/deployment.yaml",
        ]

        mock_file_contents = {
            "dockerfile": [
                '<file_content path="Dockerfile">' "\nFROM python\n</file_content>"
            ],
            "cicd-pipeline": [
                '<file_content path=".github/workflows/ci.yml">'
                "\non: push\n</file_content>"
            ],
            "terraform-iac": [
                '<file_content path="infra/main.tf">'
                '\nresource "azurerm"\n</file_content>'
            ],
            "kubernetes-manifests": [
                '<file_content path="k8s/deployment.yaml">'
                "\nkind: Deployment\n</file_content>"
            ],
        }

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

        with (
            patch(
                "services.devops_verification_service._fetch_repo_tree",
                new_callable=AsyncMock,
                return_value=mock_files,
            ),
            patch(
                "services.devops_verification_service._fetch_all_devops_files",
                new_callable=AsyncMock,
                return_value=mock_file_contents,
            ),
            patch(
                "services.devops_verification_service._analyze_with_llm",
                new_callable=AsyncMock,
                return_value=mock_validation,
            ),
        ):
            result = await analyze_devops_repository(
                "https://github.com/testuser/journal-starter",
                "testuser",
            )

        assert result.is_valid is True

    @pytest.mark.asyncio
    async def test_llm_client_error_returns_server_error(self):
        """LLMClientError should return server_error=True."""
        from core.llm_client import LLMClientError

        with (
            patch(
                "services.devops_verification_service._fetch_repo_tree",
                new_callable=AsyncMock,
                return_value=["Dockerfile"],
            ),
            patch(
                "services.devops_verification_service._fetch_all_devops_files",
                new_callable=AsyncMock,
                return_value={t["id"]: [] for t in PHASE5_TASKS},
            ),
            patch(
                "services.devops_verification_service._analyze_with_llm",
                new_callable=AsyncMock,
                side_effect=LLMClientError("Connection failed", retriable=True),
            ),
        ):
            result = await analyze_devops_repository(
                "https://github.com/testuser/journal-starter",
                "testuser",
            )

        assert result.is_valid is False
        assert result.server_error is True

    @pytest.mark.asyncio
    async def test_devops_analysis_error_returns_server_error_when_retriable(self):
        """Retriable DevOpsAnalysisError should return server_error=True."""
        with (
            patch(
                "services.devops_verification_service._fetch_repo_tree",
                new_callable=AsyncMock,
                return_value=["Dockerfile"],
            ),
            patch(
                "services.devops_verification_service._fetch_all_devops_files",
                new_callable=AsyncMock,
                return_value={t["id"]: [] for t in PHASE5_TASKS},
            ),
            patch(
                "services.devops_verification_service._analyze_with_llm",
                new_callable=AsyncMock,
                side_effect=DevOpsAnalysisError("Timeout", retriable=True),
            ),
        ):
            result = await analyze_devops_repository(
                "https://github.com/testuser/journal-starter",
                "testuser",
            )

        assert result.is_valid is False
        assert result.server_error is True
