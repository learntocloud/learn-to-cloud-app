"""Tests for pr_verification_service.

Tests cover:
- PR URL parsing (valid/invalid formats)
- Username matching (case-insensitive)
- PR merge state verification
- File change verification against expected_files
- Error handling for GitHub API failures
"""

from unittest.mock import patch

import httpx
import pytest

from models import SubmissionType
from schemas import HandsOnRequirement
from services.pr_verification_service import (
    parse_pr_url,
    validate_pr,
)


def _make_pr_requirement(
    expected_files: list[str] | None = None,
    requirement_id: str = "journal-pr-logging",
) -> HandsOnRequirement:
    """Helper to create a PR_REVIEW requirement."""
    return HandsOnRequirement(
        id=requirement_id,
        submission_type=SubmissionType.PR_REVIEW,
        name="Test PR Requirement",
        description="Test",
        placeholder="https://github.com/user/repo/pull/1",
        expected_files=expected_files,
    )


# =============================================================================
# URL Parsing Tests
# =============================================================================


@pytest.mark.unit
class TestParsePrUrl:
    """Tests for PR URL parsing."""

    def test_valid_pr_url(self):
        parsed = parse_pr_url("https://github.com/someuser/journal-starter/pull/3")
        assert parsed.is_valid
        assert parsed.owner == "someuser"
        assert parsed.repo == "journal-starter"
        assert parsed.number == 3

    def test_valid_pr_url_with_files_tab(self):
        parsed = parse_pr_url(
            "https://github.com/someuser/journal-starter/pull/3/files"
        )
        assert parsed.is_valid
        assert parsed.number == 3

    def test_valid_pr_url_with_commits_tab(self):
        parsed = parse_pr_url(
            "https://github.com/someuser/journal-starter/pull/42/commits"
        )
        assert parsed.is_valid
        assert parsed.number == 42

    def test_valid_pr_url_with_trailing_slash(self):
        parsed = parse_pr_url("https://github.com/user/repo/pull/1/")
        assert parsed.is_valid
        assert parsed.number == 1

    def test_invalid_repo_url_not_pr(self):
        parsed = parse_pr_url("https://github.com/user/repo")
        assert not parsed.is_valid
        assert "Pull Request link" in (parsed.error or "")

    def test_invalid_non_github_url(self):
        parsed = parse_pr_url("https://gitlab.com/user/repo/pull/1")
        assert not parsed.is_valid

    def test_invalid_empty_string(self):
        parsed = parse_pr_url("")
        assert not parsed.is_valid

    def test_http_protocol(self):
        parsed = parse_pr_url("http://github.com/user/repo/pull/5")
        assert parsed.is_valid
        assert parsed.number == 5


# =============================================================================
# Validation Tests
# =============================================================================


@pytest.mark.unit
class TestValidatePr:
    """Tests for the full PR validation flow."""

    @pytest.mark.asyncio
    async def test_invalid_url_fails(self):
        requirement = _make_pr_requirement(expected_files=["api/main.py"])
        result = await validate_pr(
            "https://github.com/user/repo",
            "user",
            requirement,
        )
        assert not result.is_valid
        assert "Pull Request link" in result.message

    @pytest.mark.asyncio
    async def test_username_mismatch_fails(self):
        requirement = _make_pr_requirement(expected_files=["api/main.py"])
        result = await validate_pr(
            "https://github.com/otheruser/journal-starter/pull/1",
            "myuser",
            requirement,
        )
        assert not result.is_valid
        assert "does not match" in result.message
        assert result.username_match is False

    @pytest.mark.asyncio
    async def test_username_match_is_case_insensitive(self):
        requirement = _make_pr_requirement(expected_files=["api/main.py"])
        result = await validate_pr(
            "https://github.com/MyUser/journal-starter/pull/1",
            "myuser",
            requirement,
        )
        # Should not fail on username — may fail on API call which is mocked elsewhere
        assert result.username_match is not False or "does not match" not in (
            result.message or ""
        )

    @pytest.mark.asyncio
    @patch("services.pr_verification_service._fetch_pr_data")
    async def test_open_pr_fails(self, mock_fetch):
        mock_fetch.return_value = {"merged": False, "state": "open"}
        requirement = _make_pr_requirement(expected_files=["api/main.py"])
        result = await validate_pr(
            "https://github.com/testuser/journal-starter/pull/1",
            "testuser",
            requirement,
        )
        assert not result.is_valid
        assert "still open" in result.message

    @pytest.mark.asyncio
    @patch("services.pr_verification_service._fetch_pr_data")
    async def test_closed_unmerged_pr_fails(self, mock_fetch):
        mock_fetch.return_value = {"merged": False, "state": "closed"}
        requirement = _make_pr_requirement(expected_files=["api/main.py"])
        result = await validate_pr(
            "https://github.com/testuser/journal-starter/pull/1",
            "testuser",
            requirement,
        )
        assert not result.is_valid
        assert "without merging" in result.message

    @pytest.mark.asyncio
    @patch("services.pr_verification_service._fetch_pr_files")
    @patch("services.pr_verification_service._fetch_pr_data")
    async def test_merged_pr_wrong_files_fails(self, mock_data, mock_files):
        mock_data.return_value = {
            "merged": True,
            "state": "closed",
            "head": {"ref": "feature/logging"},
            "title": "Add logging",
        }
        mock_files.return_value = ["README.md", "docs/notes.md"]
        requirement = _make_pr_requirement(expected_files=["api/main.py"])
        result = await validate_pr(
            "https://github.com/testuser/journal-starter/pull/1",
            "testuser",
            requirement,
        )
        assert not result.is_valid
        assert "didn't modify" in result.message

    @pytest.mark.asyncio
    @patch("services.pr_verification_service._fetch_pr_files")
    @patch("services.pr_verification_service._fetch_pr_data")
    async def test_merged_pr_correct_files_passes(self, mock_data, mock_files):
        mock_data.return_value = {
            "merged": True,
            "state": "closed",
            "head": {"ref": "feature/logging-setup"},
            "title": "Add logging",
        }
        mock_files.return_value = ["api/main.py", "api/other.py"]
        requirement = _make_pr_requirement(expected_files=["api/main.py"])
        result = await validate_pr(
            "https://github.com/testuser/journal-starter/pull/1",
            "testuser",
            requirement,
        )
        assert result.is_valid
        assert "verified" in result.message.lower()
        assert "feature/logging-setup" in result.message

    @pytest.mark.asyncio
    @patch("services.pr_verification_service._fetch_pr_files")
    @patch("services.pr_verification_service._fetch_pr_data")
    async def test_merged_pr_no_expected_files_passes(self, mock_data, mock_files):
        """When expected_files is None, skip file check."""
        mock_data.return_value = {
            "merged": True,
            "state": "closed",
            "head": {"ref": "my-branch"},
            "title": "Some changes",
        }
        requirement = _make_pr_requirement(expected_files=None)
        result = await validate_pr(
            "https://github.com/testuser/journal-starter/pull/1",
            "testuser",
            requirement,
        )
        assert result.is_valid
        mock_files.assert_not_called()

    @pytest.mark.asyncio
    @patch("services.pr_verification_service._fetch_pr_files")
    @patch("services.pr_verification_service._fetch_pr_data")
    async def test_file_matching_is_case_insensitive(self, mock_data, mock_files):
        mock_data.return_value = {
            "merged": True,
            "state": "closed",
            "head": {"ref": "feature/cli"},
            "title": "CLI setup",
        }
        mock_files.return_value = [".devcontainer/Devcontainer.json"]
        requirement = _make_pr_requirement(
            expected_files=[".devcontainer/devcontainer.json"]
        )
        result = await validate_pr(
            "https://github.com/testuser/journal-starter/pull/5",
            "testuser",
            requirement,
        )
        assert result.is_valid

    @pytest.mark.asyncio
    @patch("services.pr_verification_service._fetch_pr_files")
    @patch("services.pr_verification_service._fetch_pr_data")
    async def test_multi_file_requirement_any_match(self, mock_data, mock_files):
        """For ai-analysis, PR should match at least one of the expected files."""
        mock_data.return_value = {
            "merged": True,
            "state": "closed",
            "head": {"ref": "feature/ai"},
            "title": "AI analysis",
        }
        mock_files.return_value = ["api/services/llm_service.py"]
        requirement = _make_pr_requirement(
            expected_files=[
                "api/services/llm_service.py",
                "api/routers/journal_router.py",
            ]
        )
        result = await validate_pr(
            "https://github.com/testuser/journal-starter/pull/4",
            "testuser",
            requirement,
        )
        assert result.is_valid


@pytest.mark.unit
class TestValidatePrErrorHandling:
    """Tests for GitHub API error handling."""

    @pytest.mark.asyncio
    @patch("services.pr_verification_service._fetch_pr_data")
    async def test_pr_not_found_404(self, mock_fetch):
        response = httpx.Response(404, request=httpx.Request("GET", "https://test"))
        mock_fetch.side_effect = httpx.HTTPStatusError(
            "Not Found", request=response.request, response=response
        )
        requirement = _make_pr_requirement(expected_files=["api/main.py"])
        result = await validate_pr(
            "https://github.com/testuser/journal-starter/pull/999",
            "testuser",
            requirement,
        )
        assert not result.is_valid
        assert "not found" in result.message.lower()
        assert result.server_error is not True

    @pytest.mark.asyncio
    @patch("services.pr_verification_service._fetch_pr_data")
    async def test_github_server_error_marks_server_error(self, mock_fetch):
        response = httpx.Response(500, request=httpx.Request("GET", "https://test"))
        mock_fetch.side_effect = httpx.HTTPStatusError(
            "Server Error", request=response.request, response=response
        )
        requirement = _make_pr_requirement(expected_files=["api/main.py"])
        result = await validate_pr(
            "https://github.com/testuser/journal-starter/pull/1",
            "testuser",
            requirement,
        )
        assert not result.is_valid
        assert result.server_error is True
