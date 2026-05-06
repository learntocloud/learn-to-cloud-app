"""Tests for repo_utils shared utilities.

Tests cover:
- GitHub URL parsing and validation (extract_repo_info)
- Repository ownership validation (validate_repo_url)
- Feedback sanitization (sanitize_feedback)
"""

import pytest

from learn_to_cloud_shared.schemas import ValidationResult
from learn_to_cloud_shared.verification.repo_utils import (
    extract_repo_info,
    sanitize_feedback,
    validate_repo_url,
)

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

    def test_www_github_url(self):
        owner, repo = extract_repo_info("https://www.github.com/testuser/my-repo")
        assert owner == "testuser"
        assert repo == "my-repo"

    def test_http_url(self):
        owner, repo = extract_repo_info("http://github.com/testuser/my-repo")
        assert owner == "testuser"
        assert repo == "my-repo"

    def test_query_string_stripped(self):
        owner, repo = extract_repo_info(
            "https://github.com/testuser/my-repo?tab=readme"
        )
        assert owner == "testuser"
        assert repo == "my-repo"

    def test_fragment_stripped(self):
        owner, repo = extract_repo_info("https://github.com/testuser/my-repo#readme")
        assert owner == "testuser"
        assert repo == "my-repo"

    def test_bare_github_url_without_scheme(self):
        owner, repo = extract_repo_info("github.com/testuser/my-repo")
        assert owner == "testuser"
        assert repo == "my-repo"


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
        assert isinstance(result, ValidationResult)
        assert result.is_valid is False
        assert "does not match" in result.message

    def test_invalid_url_returns_validation_result(self):
        result = validate_repo_url("not-a-url", "testuser")
        assert isinstance(result, ValidationResult)
        assert result.is_valid is False
        assert "Invalid GitHub repository URL" in result.message

    def test_expected_repo_name_match(self):
        result = validate_repo_url(
            "https://github.com/testuser/journal-starter",
            "testuser",
            expected_repo_name="journal-starter",
        )
        assert result == ("testuser", "journal-starter")

    def test_expected_repo_name_case_insensitive_match(self):
        result = validate_repo_url(
            "https://github.com/testuser/Journal-Starter",
            "testuser",
            expected_repo_name="journal-starter",
        )
        assert result == ("testuser", "Journal-Starter")

    def test_expected_repo_name_mismatch_returns_validation_result(self):
        result = validate_repo_url(
            "https://github.com/testuser/wrong-repo",
            "testuser",
            expected_repo_name="journal-starter",
        )
        assert isinstance(result, ValidationResult)
        assert result.is_valid is False
        assert "does not match the expected fork name" in result.message
        assert result.username_match is True


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
