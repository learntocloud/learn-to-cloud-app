"""Tests for llm_verification_base shared utilities.

Tests cover:
- GitHub URL parsing and validation (extract_repo_info)
- Repository ownership validation (validate_repo_url)
- Feedback sanitization (sanitize_feedback)
- Generic structured response parsing (parse_structured_response)
- Generic task result building (build_task_results)
"""

import json
from unittest.mock import MagicMock

import pytest
from pydantic import BaseModel, Field

from services.llm_verification_base import (
    SUSPICIOUS_PATTERNS,
    VerificationError,
    build_task_results,
    extract_repo_info,
    parse_structured_response,
    sanitize_feedback,
    validate_repo_url,
)

# ---------------------------------------------------------------------------
# Test helpers — minimal Pydantic models for parse_structured_response
# ---------------------------------------------------------------------------


class _FakeGrade(BaseModel):
    task_id: str
    passed: bool
    feedback: str = ""


class _FakeAnalysisResponse(BaseModel):
    tasks: list[_FakeGrade] = Field(min_length=1)


class _FakeError(VerificationError):
    """Test-only error subclass."""


# ---------------------------------------------------------------------------
# extract_repo_info
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestExtractRepoInfo:
    """Tests for GitHub URL parsing."""

    def test_standard_url(self):
        owner, repo = extract_repo_info("https://github.com/testuser/journal-starter")
        assert owner == "testuser"
        assert repo == "journal-starter"

    def test_url_with_trailing_slash(self):
        owner, repo = extract_repo_info("https://github.com/testuser/journal-starter/")
        assert owner == "testuser"
        assert repo == "journal-starter"

    def test_url_with_git_suffix(self):
        owner, repo = extract_repo_info(
            "https://github.com/testuser/journal-starter.git"
        )
        assert owner == "testuser"
        assert repo == "journal-starter"

    def test_url_with_subpath(self):
        owner, repo = extract_repo_info(
            "https://github.com/testuser/journal-starter/tree/main/infra"
        )
        assert owner == "testuser"
        assert repo == "journal-starter"

    def test_url_with_whitespace(self):
        owner, repo = extract_repo_info(
            "  https://github.com/testuser/journal-starter  "
        )
        assert owner == "testuser"
        assert repo == "journal-starter"

    def test_invalid_url_raises(self):
        with pytest.raises(ValueError, match="Invalid GitHub repository URL"):
            extract_repo_info("https://gitlab.com/testuser/repo")

    def test_empty_url_raises(self):
        with pytest.raises(ValueError, match="Invalid GitHub repository URL"):
            extract_repo_info("")

    def test_non_url_raises(self):
        with pytest.raises(ValueError, match="Invalid GitHub repository URL"):
            extract_repo_info("not-a-url")


# ---------------------------------------------------------------------------
# validate_repo_url
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestValidateRepoUrl:
    """Tests for URL parsing + ownership validation."""

    def test_valid_url_matching_username(self):
        result = validate_repo_url(
            "https://github.com/testuser/journal-starter", "testuser"
        )
        assert result == ("testuser", "journal-starter")

    def test_case_insensitive_match(self):
        result = validate_repo_url(
            "https://github.com/TestUser/journal-starter", "testuser"
        )
        assert result == ("TestUser", "journal-starter")

    def test_username_mismatch_returns_validation_result(self):
        result = validate_repo_url(
            "https://github.com/otheruser/journal-starter", "testuser"
        )
        assert hasattr(result, "is_valid")
        assert result.is_valid is False
        assert "does not match" in result.message

    def test_invalid_url_returns_validation_result(self):
        result = validate_repo_url("not-a-url", "testuser")
        assert hasattr(result, "is_valid")
        assert result.is_valid is False
        assert "Invalid GitHub repository URL" in result.message


# ---------------------------------------------------------------------------
# sanitize_feedback
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestSanitizeFeedback:
    """Tests for feedback sanitization security function."""

    def test_normal_feedback_unchanged(self):
        feedback = "Good job! You implemented logging correctly."
        assert sanitize_feedback(feedback) == feedback

    def test_empty_feedback_returns_default(self):
        assert sanitize_feedback("") == "No feedback provided"
        assert sanitize_feedback(None) == "No feedback provided"

    def test_long_feedback_truncated(self):
        long_feedback = "x" * 1000
        result = sanitize_feedback(long_feedback)
        assert len(result) <= 503  # 500 + "..."

    def test_html_tags_stripped(self):
        feedback = "Good <script>alert('xss')</script> job!"
        result = sanitize_feedback(feedback)
        assert "<script>" not in result
        assert "</script>" not in result
        assert "Good" in result
        assert "job!" in result

    def test_code_blocks_replaced(self):
        feedback = "Check this: ```python\nprint('injection')```"
        result = sanitize_feedback(feedback)
        assert "```" not in result
        assert "[code snippet]" in result

    def test_urls_removed(self):
        feedback = "Visit https://malicious.com for more info"
        result = sanitize_feedback(feedback)
        assert "https://malicious.com" not in result
        assert "[link removed]" in result

    def test_whitespace_only_returns_default(self):
        assert sanitize_feedback("   ") == "No feedback provided"


# ---------------------------------------------------------------------------
# SUSPICIOUS_PATTERNS
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestSuspiciousPatterns:
    """Tests for prompt injection detection patterns."""

    def test_suspicious_patterns_defined(self):
        assert len(SUSPICIOUS_PATTERNS) > 0
        assert "ignore all previous" in SUSPICIOUS_PATTERNS
        assert "system prompt" in SUSPICIOUS_PATTERNS


# ---------------------------------------------------------------------------
# parse_structured_response
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestParseStructuredResponse:
    """Tests for generic structured response parsing."""

    def test_parses_from_value_direct_instance(self):
        expected = _FakeAnalysisResponse(
            tasks=[_FakeGrade(task_id="t1", passed=True, feedback="OK")]
        )
        mock_result = MagicMock()
        mock_result.value = expected
        mock_result.text = ""

        result = parse_structured_response(
            mock_result, _FakeAnalysisResponse, _FakeError, "test"
        )
        assert result is expected

    def test_parses_from_value_dict(self):
        mock_result = MagicMock()
        mock_result.value = {
            "tasks": [{"task_id": "t1", "passed": True, "feedback": "OK"}]
        }
        mock_result.text = ""

        result = parse_structured_response(
            mock_result, _FakeAnalysisResponse, _FakeError, "test"
        )
        assert len(result.tasks) == 1

    def test_fallback_to_text_parsing(self):
        mock_result = MagicMock()
        mock_result.value = None
        mock_result.text = json.dumps(
            {"tasks": [{"task_id": "t1", "passed": True, "feedback": "OK"}]}
        )

        result = parse_structured_response(
            mock_result, _FakeAnalysisResponse, _FakeError, "test"
        )
        assert len(result.tasks) == 1

    def test_empty_text_raises(self):
        mock_result = MagicMock()
        mock_result.value = None
        mock_result.text = ""

        with pytest.raises(_FakeError, match="No response received"):
            parse_structured_response(
                mock_result, _FakeAnalysisResponse, _FakeError, "test"
            )

    def test_invalid_text_raises(self):
        mock_result = MagicMock()
        mock_result.value = None
        mock_result.text = "not json at all"

        with pytest.raises(_FakeError, match="Could not parse"):
            parse_structured_response(
                mock_result, _FakeAnalysisResponse, _FakeError, "test"
            )


# ---------------------------------------------------------------------------
# build_task_results
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestBuildTaskResults:
    """Tests for generic task result building."""

    _TASKS = [
        {"id": "task-a", "name": "Task A"},
        {"id": "task-b", "name": "Task B"},
    ]

    def test_all_passed(self):
        grades = [
            _FakeGrade(task_id="task-a", passed=True, feedback="Done"),
            _FakeGrade(task_id="task-b", passed=True, feedback="Done"),
        ]
        results, all_passed = build_task_results(grades, self._TASKS)
        assert all_passed is True
        assert len(results) == 2

    def test_some_failed(self):
        grades = [
            _FakeGrade(task_id="task-a", passed=True, feedback="Done"),
            _FakeGrade(task_id="task-b", passed=False, feedback="Missing"),
        ]
        results, all_passed = build_task_results(grades, self._TASKS)
        assert all_passed is False

    def test_missing_tasks_filled(self):
        grades = [
            _FakeGrade(task_id="task-a", passed=True, feedback="Done"),
        ]
        results, all_passed = build_task_results(grades, self._TASKS)
        assert all_passed is False
        assert len(results) == 2
        missing = next(r for r in results if r.task_name == "Task B")
        assert missing.passed is False
        assert "not evaluated" in missing.feedback.lower()

    def test_feedback_sanitized(self):
        grades = [
            _FakeGrade(
                task_id="task-a",
                passed=True,
                feedback="Visit <script>evil</script> https://bad.com",
            ),
            _FakeGrade(task_id="task-b", passed=True, feedback="OK"),
        ]
        results, _ = build_task_results(grades, self._TASKS)
        task_a = next(r for r in results if r.task_name == "Task A")
        assert "<script>" not in task_a.feedback
        assert "https://bad.com" not in task_a.feedback

    def test_unknown_task_ids_ignored(self):
        grades = [
            _FakeGrade(task_id="task-a", passed=True, feedback="Done"),
            _FakeGrade(task_id="unknown", passed=True, feedback="Huh"),
            _FakeGrade(task_id="task-b", passed=True, feedback="Done"),
        ]
        results, all_passed = build_task_results(grades, self._TASKS)
        assert all_passed is True
        assert len(results) == 2
