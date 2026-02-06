"""Unit tests for devops_verification_service.

Tests cover:
- GitHub URL parsing and validation
- Repository file tree filtering
- Prompt construction
- Copilot response parsing
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
    _build_task_results,
    _build_verification_prompt,
    _extract_repo_info,
    _filter_devops_files,
    _parse_analysis_response,
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
class TestParseAnalysisResponse:
    """Tests for Copilot response parsing."""

    def test_valid_json_response(self):
        task = {
            "task_id": "dockerfile",
            "passed": True,
            "feedback": "Good",
        }
        response = json.dumps({"tasks": [task]})
        result = _parse_analysis_response(response)
        assert len(result) == 1
        assert result[0]["task_id"] == "dockerfile"
        assert result[0]["passed"] is True

    def test_json_in_code_block(self):
        task = {
            "task_id": "dockerfile",
            "passed": True,
            "feedback": "Good",
        }
        payload = json.dumps({"tasks": [task]})
        response = f"```json\n{payload}\n```"
        result = _parse_analysis_response(response)
        assert len(result) == 1

    def test_full_response_with_all_tasks(self):
        tasks = [
            {"task_id": t["id"], "passed": True, "feedback": f"{t['name']} done"}
            for t in PHASE5_TASKS
        ]
        response = json.dumps({"tasks": tasks})
        result = _parse_analysis_response(response)
        assert len(result) == 4

    def test_missing_tasks_field_raises(self):
        with pytest.raises(DevOpsAnalysisError, match="not a list"):
            _parse_analysis_response('{"tasks": "not a list"}')

    def test_no_json_raises(self):
        with pytest.raises(DevOpsAnalysisError, match="Could not extract JSON"):
            _parse_analysis_response("This is just plain text with no JSON")

    def test_invalid_json_raises(self):
        with pytest.raises(DevOpsAnalysisError, match="Invalid JSON"):
            _parse_analysis_response('{"tasks": [invalid]}')

    def test_tasks_not_list_raises(self):
        with pytest.raises(DevOpsAnalysisError, match="not a list"):
            _parse_analysis_response('{"tasks": "not a list"}')


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
        parsed = [
            {"task_id": t["id"], "passed": True, "feedback": "Done"}
            for t in PHASE5_TASKS
        ]
        results, all_passed = _build_task_results(parsed)
        assert all_passed is True
        assert len(results) == 4

    def test_some_failed(self):
        parsed = [
            {"task_id": "dockerfile", "passed": True, "feedback": "Done"},
            {"task_id": "cicd-pipeline", "passed": False, "feedback": "Missing"},
            {"task_id": "terraform-iac", "passed": True, "feedback": "Done"},
            {"task_id": "kubernetes-manifests", "passed": False, "feedback": "Missing"},
        ]
        results, all_passed = _build_task_results(parsed)
        assert all_passed is False
        assert sum(1 for r in results if r.passed) == 2

    def test_missing_tasks_are_failed(self):
        """Tasks not in the response should be marked as failed."""
        parsed = [
            {"task_id": "dockerfile", "passed": True, "feedback": "Done"},
        ]
        results, all_passed = _build_task_results(parsed)
        assert all_passed is False
        assert len(results) == 4  # All 4 tasks present
        failed = [r for r in results if not r.passed]
        assert len(failed) == 3

    def test_invalid_task_ids_skipped(self):
        parsed = [
            {"task_id": "invalid-id", "passed": True, "feedback": "Done"},
        ]
        results, all_passed = _build_task_results(parsed)
        # All 4 tasks should be missing → failed
        assert all_passed is False
        assert len(results) == 4
        assert all(not r.passed for r in results)

    def test_string_passed_converted_to_bool(self):
        parsed = [
            {"task_id": "dockerfile", "passed": "true", "feedback": "Done"},
        ]
        results, _ = _build_task_results(parsed)
        dockerfile_result = next(
            r for r in results if r.task_name == "Containerization (Dockerfile)"
        )
        assert dockerfile_result.passed is True


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
                "services.devops_verification_service._analyze_with_copilot",
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
    async def test_copilot_client_error_returns_server_error(self):
        """CopilotClientError should return server_error=True."""
        from core.copilot_client import CopilotClientError

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
                "services.devops_verification_service._analyze_with_copilot",
                new_callable=AsyncMock,
                side_effect=CopilotClientError("Connection failed", retriable=True),
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
                "services.devops_verification_service._analyze_with_copilot",
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
