"""Tests for copilot_verification_service.py.

Tests for the Phase 2 AI-powered code verification service.
The Copilot SDK interactions are mocked since the SDK requires
external CLI server connectivity.
"""

import json
from unittest.mock import MagicMock, patch

import httpx
import pytest
from circuitbreaker import CircuitBreakerError

from schemas import TaskResult
from services.copilot_verification_service import (
    PHASE2_TASKS,
    CodeAnalysisError,
    _build_task_results,
    _build_verification_prompt,
    _extract_repo_info,
    _fetch_github_file_content,
    _parse_analysis_response,
    analyze_repository_code,
)


class TestExtractRepoInfo:
    """Tests for _extract_repo_info()."""

    def test_extracts_from_https_url(self):
        """Should extract owner and repo from HTTPS URL."""
        owner, repo = _extract_repo_info("https://github.com/testuser/journal-starter")
        assert owner == "testuser"
        assert repo == "journal-starter"

    def test_extracts_from_url_with_trailing_slash(self):
        """Should handle trailing slash."""
        owner, repo = _extract_repo_info("https://github.com/testuser/journal-starter/")
        assert owner == "testuser"
        assert repo == "journal-starter"

    def test_extracts_from_url_with_subpath(self):
        """Should extract from URL with additional path segments."""
        owner, repo = _extract_repo_info(
            "https://github.com/testuser/journal-starter/tree/main/api"
        )
        assert owner == "testuser"
        assert repo == "journal-starter"

    def test_removes_git_suffix(self):
        """Should remove .git suffix from repo name."""
        owner, repo = _extract_repo_info(
            "https://github.com/testuser/journal-starter.git"
        )
        assert owner == "testuser"
        assert repo == "journal-starter"

    def test_handles_url_without_protocol(self):
        """Should handle URL without https:// prefix."""
        owner, repo = _extract_repo_info("github.com/testuser/journal-starter")
        assert owner == "testuser"
        assert repo == "journal-starter"

    def test_raises_for_invalid_url(self):
        """Should raise ValueError for non-GitHub URL."""
        with pytest.raises(ValueError, match="Invalid GitHub repository URL"):
            _extract_repo_info("https://gitlab.com/user/repo")

    def test_raises_for_malformed_url(self):
        """Should raise ValueError for malformed URL."""
        with pytest.raises(ValueError, match="Invalid GitHub repository URL"):
            _extract_repo_info("not-a-url")


class TestBuildVerificationPrompt:
    """Tests for _build_verification_prompt()."""

    def test_includes_owner_and_repo(self):
        """Should include repository owner and name in prompt."""
        prompt = _build_verification_prompt("testuser", "journal-starter")
        assert "testuser/journal-starter" in prompt

    def test_includes_all_task_names(self):
        """Should include all task names from PHASE2_TASKS."""
        prompt = _build_verification_prompt("owner", "repo")
        for task in PHASE2_TASKS:
            assert task["name"] in prompt

    def test_includes_json_format_instructions(self):
        """Should include JSON response format instructions."""
        prompt = _build_verification_prompt("owner", "repo")
        assert "JSON" in prompt
        assert '"tasks"' in prompt
        assert '"task_id"' in prompt
        assert '"passed"' in prompt
        assert '"feedback"' in prompt


class TestParseAnalysisResponse:
    """Tests for _parse_analysis_response()."""

    def test_parses_valid_json_response(self):
        """Should parse valid JSON with tasks array."""
        response = json.dumps(
            {
                "tasks": [
                    {"task_id": "logging-setup", "passed": True, "feedback": "Good"},
                    {
                        "task_id": "get-single-entry",
                        "passed": False,
                        "feedback": "Missing",
                    },
                ]
            }
        )
        result = _parse_analysis_response(response)
        assert len(result) == 2
        assert result[0]["task_id"] == "logging-setup"
        assert result[0]["passed"] is True

    def test_parses_json_wrapped_in_markdown(self):
        """Should extract JSON from markdown code block."""
        response = """
Here is my analysis:

```json
{"tasks": [{"task_id": "test", "passed": true, "feedback": "OK"}]}
```

Done!
"""
        result = _parse_analysis_response(response)
        assert len(result) == 1
        assert result[0]["task_id"] == "test"

    def test_raises_for_no_json_found(self):
        """Should raise CodeAnalysisError if no JSON object found."""
        response = "This response has no JSON at all"
        with pytest.raises(CodeAnalysisError, match="Could not extract JSON"):
            _parse_analysis_response(response)

    def test_raises_for_invalid_json(self):
        """Should raise CodeAnalysisError for invalid JSON."""
        response = "This is not JSON at all"
        with pytest.raises(CodeAnalysisError, match="Could not extract JSON"):
            _parse_analysis_response(response)


class TestBuildTaskResults:
    """Tests for _build_task_results()."""

    def test_converts_parsed_tasks_to_task_results(self):
        """Should convert parsed task dicts to TaskResult objects."""
        parsed = [
            {"task_id": "logging-setup", "passed": True, "feedback": "Configured"},
            {"task_id": "get-single-entry", "passed": False, "feedback": "Missing 404"},
        ]
        results, all_passed = _build_task_results(parsed)

        assert len(results) >= 2
        assert isinstance(results[0], TaskResult)
        assert results[0].task_name == "Logging Setup"
        assert results[0].passed is True
        assert all_passed is False  # One task failed

    def test_all_passed_true_when_all_tasks_pass(self):
        """Should return all_passed=True when all tasks pass."""
        parsed = [
            {"task_id": task["id"], "passed": True, "feedback": "OK"}
            for task in PHASE2_TASKS
        ]
        results, all_passed = _build_task_results(parsed)
        assert all_passed is True

    def test_adds_missing_tasks_as_failed(self):
        """Should add missing tasks as failed with appropriate message."""
        parsed = [{"task_id": "logging-setup", "passed": True, "feedback": "OK"}]
        results, all_passed = _build_task_results(parsed)

        # Should have entries for all 5 tasks
        assert len(results) == 5
        assert all_passed is False

        # Missing tasks should be marked as not evaluated
        missing_results = [r for r in results if "not evaluated" in r.feedback]
        assert len(missing_results) == 4


class TestFetchGitHubFileContent:
    """Tests for _fetch_github_file_content()."""

    @pytest.mark.asyncio
    async def test_fetches_file_from_raw_githubusercontent(self, respx_mock):
        """Should fetch file content from raw.githubusercontent.com."""
        respx_mock.get(
            "https://raw.githubusercontent.com/owner/repo/main/README.md"
        ).mock(return_value=httpx.Response(200, text="# README"))

        content = await _fetch_github_file_content("owner", "repo", "README.md")
        assert content == "# README"

    @pytest.mark.asyncio
    async def test_uses_specified_branch(self, respx_mock):
        """Should use specified branch in URL."""
        respx_mock.get(
            "https://raw.githubusercontent.com/owner/repo/develop/file.py"
        ).mock(return_value=httpx.Response(200, text="content"))

        content = await _fetch_github_file_content(
            "owner", "repo", "file.py", branch="develop"
        )
        assert content == "content"

    @pytest.mark.asyncio
    async def test_raises_on_404(self, respx_mock):
        """Should raise HTTPStatusError for 404."""
        respx_mock.get(
            "https://raw.githubusercontent.com/owner/repo/main/missing.txt"
        ).mock(return_value=httpx.Response(404))

        with pytest.raises(httpx.HTTPStatusError):
            await _fetch_github_file_content("owner", "repo", "missing.txt")


class TestAnalyzeRepositoryCode:
    """Tests for analyze_repository_code() main entry point."""

    @pytest.mark.asyncio
    async def test_returns_invalid_for_bad_url(self):
        """Should return invalid result for non-GitHub URL."""
        result = await analyze_repository_code(
            "https://gitlab.com/user/repo", "testuser"
        )

        assert result.is_valid is False
        assert "Invalid GitHub repository URL" in result.message

    @pytest.mark.asyncio
    async def test_returns_invalid_for_username_mismatch(self):
        """Should return invalid if repo owner doesn't match username."""
        result = await analyze_repository_code(
            "https://github.com/otheruser/journal-starter", "testuser"
        )

        assert result.is_valid is False
        assert "does not match" in result.message
        assert result.username_match is False

    @pytest.mark.asyncio
    async def test_handles_circuit_breaker_error(self):
        """Should return user-friendly message when circuit breaker is open."""
        with patch(
            "services.copilot_verification_service._analyze_with_copilot",
            side_effect=CircuitBreakerError(MagicMock()),
        ):
            result = await analyze_repository_code(
                "https://github.com/testuser/journal-starter", "testuser"
            )

        assert result.is_valid is False
        assert "temporarily unavailable" in result.message

    @pytest.mark.asyncio
    async def test_handles_code_analysis_error(self):
        """Should return error message on CodeAnalysisError."""
        with patch(
            "services.copilot_verification_service._analyze_with_copilot",
            side_effect=CodeAnalysisError("Test error", retriable=True),
        ):
            result = await analyze_repository_code(
                "https://github.com/testuser/journal-starter", "testuser"
            )

        assert result.is_valid is False
        assert "Test error" in result.message


class TestPhase2Tasks:
    """Tests for PHASE2_TASKS configuration."""

    def test_has_five_tasks(self):
        """Should have exactly 5 required tasks."""
        assert len(PHASE2_TASKS) == 5

    def test_all_tasks_have_required_fields(self):
        """All tasks should have id, name, and criteria."""
        for task in PHASE2_TASKS:
            assert "id" in task
            assert "name" in task
            assert "criteria" in task
            assert len(task["criteria"]) > 0

    def test_task_ids_are_unique(self):
        """Task IDs should be unique."""
        ids = [task["id"] for task in PHASE2_TASKS]
        assert len(ids) == len(set(ids))
