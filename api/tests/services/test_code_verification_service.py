"""Tests for code_verification_service security and grading features.

Tests cover:
- File allowlist enforcement (security)
- Feedback sanitization (security)
- Task result building (grading)
- Prompt injection detection (security)
"""

import pytest

from services.code_verification_service import (
    ALLOWED_FILE_PATHS,
    PHASE3_TASKS,
    SUSPICIOUS_PATTERNS,
    _build_task_results,
    _sanitize_feedback,
)


@pytest.mark.unit
class TestAllowedFilePaths:
    """Tests for file allowlist configuration."""

    def test_allowlist_contains_expected_files(self):
        """Allowlist should contain exactly the files we need to grade."""
        expected = {
            "api/main.py",
            "api/routers/journal_router.py",
            "api/services/llm_service.py",
            ".devcontainer/devcontainer.json",
        }
        assert ALLOWED_FILE_PATHS == expected

    def test_allowlist_is_frozen(self):
        """Allowlist should be immutable to prevent runtime modification."""
        assert isinstance(ALLOWED_FILE_PATHS, frozenset)


@pytest.mark.unit
class TestPhase3Tasks:
    """Tests for task definitions."""

    def test_all_tasks_have_required_fields(self):
        """Each task must have id, name, and criteria."""
        for task in PHASE3_TASKS:
            assert "id" in task, f"Task missing id: {task}"
            assert "name" in task, f"Task missing name: {task}"
            assert "criteria" in task, f"Task missing criteria: {task}"

    def test_all_tasks_have_file_reference(self):
        """Each task must specify file or files to check."""
        for task in PHASE3_TASKS:
            has_file = "file" in task or "files" in task
            assert has_file, f"Task {task['id']} missing file reference"

    def test_all_tasks_have_grading_hints(self):
        """Each task should have pass/fail indicators for deterministic grading."""
        for task in PHASE3_TASKS:
            assert (
                "pass_indicators" in task
            ), f"Task {task['id']} missing pass_indicators"
            assert (
                "fail_indicators" in task
            ), f"Task {task['id']} missing fail_indicators"
            assert (
                "starter_code_hint" in task
            ), f"Task {task['id']} missing starter_code_hint"

    def test_task_ids_are_unique(self):
        """Task IDs must be unique."""
        ids = [task["id"] for task in PHASE3_TASKS]
        assert len(ids) == len(set(ids)), "Duplicate task IDs found"

    def test_expected_task_count(self):
        """Should have exactly 5 tasks for Phase 3."""
        assert len(PHASE3_TASKS) == 5


@pytest.mark.unit
class TestSuspiciousPatterns:
    """Tests for prompt injection detection patterns."""

    def test_suspicious_patterns_defined(self):
        """Should have patterns to detect common injection attempts."""
        assert len(SUSPICIOUS_PATTERNS) > 0
        assert "ignore all previous" in SUSPICIOUS_PATTERNS
        assert "system prompt" in SUSPICIOUS_PATTERNS


@pytest.mark.unit
class TestSanitizeFeedback:
    """Tests for feedback sanitization security function."""

    def test_normal_feedback_unchanged(self):
        """Normal feedback should pass through unchanged."""
        feedback = "Good job! You implemented logging correctly."
        assert _sanitize_feedback(feedback) == feedback

    def test_empty_feedback_returns_default(self):
        """Empty or None feedback returns default message."""
        assert _sanitize_feedback("") == "No feedback provided"
        assert _sanitize_feedback(None) == "No feedback provided"

    def test_long_feedback_truncated(self):
        """Excessively long feedback should be truncated."""
        long_feedback = "x" * 1000
        result = _sanitize_feedback(long_feedback)
        assert len(result) <= 503  # 500 + "..."

    def test_html_tags_stripped(self):
        """HTML/XML tags should be removed."""
        feedback = "Good <script>alert('xss')</script> job!"
        result = _sanitize_feedback(feedback)
        assert "<script>" not in result
        assert "</script>" not in result
        # Content between tags is preserved (just tags removed)
        assert "Good" in result
        assert "job!" in result

    def test_code_blocks_replaced(self):
        """Markdown code blocks should be replaced."""
        feedback = "Check this: ```python\nprint('injection')```"
        result = _sanitize_feedback(feedback)
        assert "```" not in result
        assert "[code snippet]" in result

    def test_urls_removed(self):
        """URLs should be removed to prevent phishing."""
        feedback = "Visit https://malicious.com for more info"
        result = _sanitize_feedback(feedback)
        assert "https://malicious.com" not in result
        assert "[link removed]" in result

    def test_whitespace_only_returns_default(self):
        """Whitespace-only feedback returns default."""
        assert _sanitize_feedback("   ") == "No feedback provided"


@pytest.mark.unit
class TestBuildTaskResults:
    """Tests for task result building with validation."""

    def test_valid_results_parsed(self):
        """Valid task results should be parsed correctly."""
        parsed = [
            {"task_id": "logging-setup", "passed": True, "feedback": "Good logging!"},
            {"task_id": "get-single-entry", "passed": False, "feedback": "Missing 404"},
        ]
        results, all_passed = _build_task_results(parsed)

        assert len(results) == 5  # All 5 tasks, missing ones filled in
        assert not all_passed  # One failed

        logging_result = next(r for r in results if r.task_name == "Logging Setup")
        assert logging_result.passed is True
        assert logging_result.feedback == "Good logging!"

    def test_invalid_task_ids_ignored(self):
        """Task IDs not in PHASE3_TASKS should be ignored."""
        parsed = [
            {"task_id": "fake-task", "passed": True, "feedback": "Injected!"},
            {"task_id": "logging-setup", "passed": True, "feedback": "Real task"},
        ]
        results, all_passed = _build_task_results(parsed)

        # Should not include fake-task
        task_names = [r.task_name for r in results]
        assert "fake-task" not in task_names
        assert "Logging Setup" in task_names

    def test_missing_tasks_filled_with_not_evaluated(self):
        """Tasks not in response should show as not evaluated."""
        parsed = [
            {"task_id": "logging-setup", "passed": True, "feedback": "Done"},
        ]
        results, all_passed = _build_task_results(parsed)

        assert not all_passed  # Missing tasks = not passed

        get_entry = next(
            r for r in results if r.task_name == "GET Single Entry Endpoint"
        )
        assert get_entry.passed is False
        assert "not evaluated" in get_entry.feedback.lower()

    def test_feedback_sanitized_in_results(self):
        """Feedback should be sanitized in results."""
        parsed = [
            {
                "task_id": "logging-setup",
                "passed": True,
                "feedback": "Visit <script>evil</script> https://bad.com",
            },
        ]
        results, _ = _build_task_results(parsed)

        logging_result = next(r for r in results if r.task_name == "Logging Setup")
        assert "<script>" not in logging_result.feedback
        assert "https://bad.com" not in logging_result.feedback

    def test_passed_coerced_to_boolean(self):
        """Non-boolean passed values should be coerced."""
        parsed = [
            {"task_id": "logging-setup", "passed": "true", "feedback": "OK"},
            {"task_id": "get-single-entry", "passed": "false", "feedback": "No"},
        ]
        results, _ = _build_task_results(parsed)

        logging_result = next(r for r in results if r.task_name == "Logging Setup")
        get_result = next(
            r for r in results if r.task_name == "GET Single Entry Endpoint"
        )

        assert logging_result.passed is True
        assert get_result.passed is False

    def test_all_passed_only_when_all_five_pass(self):
        """all_passed should be True only when all 5 tasks pass."""
        all_pass = [
            {"task_id": "logging-setup", "passed": True, "feedback": "OK"},
            {"task_id": "get-single-entry", "passed": True, "feedback": "OK"},
            {"task_id": "delete-entry", "passed": True, "feedback": "OK"},
            {"task_id": "ai-analysis", "passed": True, "feedback": "OK"},
            {"task_id": "cloud-cli-setup", "passed": True, "feedback": "OK"},
        ]
        results, all_passed = _build_task_results(all_pass)

        assert all_passed is True
        assert all(r.passed for r in results)
