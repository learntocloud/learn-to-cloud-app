"""Tests for pr_verification_service.

Tests cover:
- PR merge state verification
- Error handling for GitHub API failures
- Deterministic indicator-based grading
"""

from unittest.mock import patch

import httpx
import pytest

from models import SubmissionType
from schemas import HandsOnRequirement
from services.verification.pull_request import validate_pr


def _make_pr_requirement(
    requirement_id: str = "journal-pr-logging",
    pass_indicators: list[str] | None = None,
    fail_indicators: list[str] | None = None,
    expected_files: list[str] | None = None,
) -> HandsOnRequirement:
    """Helper to create a PR_REVIEW requirement."""
    return HandsOnRequirement(
        id=requirement_id,
        submission_type=SubmissionType.PR_REVIEW,
        name="Test PR Requirement",
        description="Test",
        placeholder="https://github.com/user/repo/pull/1",
        grading_criteria=["MUST have meaningful changes"],
        pass_indicators=pass_indicators or ["import logging"],
        fail_indicators=fail_indicators,
        expected_files=expected_files,
    )


_TEST_PR_URL = "https://github.com/testuser/journal-starter/pull/1"


# =============================================================================
# Validation Tests
# =============================================================================


@pytest.mark.unit
class TestValidatePr:
    """Tests for the full PR validation flow."""

    @pytest.mark.asyncio
    @patch("services.verification.pull_request._fetch_pr_data", autospec=True)
    async def test_open_pr_fails(self, mock_fetch):
        mock_fetch.return_value = {"merged": False, "state": "open"}
        result = await validate_pr(_TEST_PR_URL, _make_pr_requirement())
        assert not result.is_valid
        assert "still open" in result.message

    @pytest.mark.asyncio
    @patch("services.verification.pull_request._fetch_pr_data", autospec=True)
    async def test_closed_unmerged_pr_fails(self, mock_fetch):
        mock_fetch.return_value = {"merged": False, "state": "closed"}
        result = await validate_pr(_TEST_PR_URL, _make_pr_requirement())
        assert not result.is_valid
        assert "without merging" in result.message

    @pytest.mark.asyncio
    @patch("services.verification.pull_request._fetch_pr_diff", autospec=True)
    @patch("services.verification.pull_request._fetch_pr_data", autospec=True)
    async def test_merged_pr_with_missing_indicators_fails(self, mock_data, mock_diff):
        """Merged PR missing pass indicators fails deterministically."""
        mock_data.return_value = {
            "merged": True,
            "state": "closed",
            "head": {"ref": "feature/logging-setup"},
        }
        mock_diff.return_value = "+some unrelated code"
        result = await validate_pr(
            _TEST_PR_URL,
            _make_pr_requirement(pass_indicators=["import logging"]),
        )
        assert not result.is_valid
        assert result.task_results
        assert not result.task_results[0].passed

    @pytest.mark.asyncio
    @patch("services.verification.pull_request._fetch_pr_diff", autospec=True)
    @patch("services.verification.pull_request._fetch_pr_data", autospec=True)
    async def test_merged_pr_with_fail_indicator_fails(self, mock_data, mock_diff):
        """Merged PR with fail indicator present fails deterministically."""
        mock_data.return_value = {
            "merged": True,
            "state": "closed",
            "head": {"ref": "feature/logging-setup"},
        }
        mock_diff.return_value = "+# TODO (Task 1): Configure logging here."
        result = await validate_pr(
            _TEST_PR_URL,
            _make_pr_requirement(
                pass_indicators=["import logging"],
                fail_indicators=["# TODO (Task 1): Configure logging here."],
            ),
        )
        assert not result.is_valid
        assert "starter/placeholder" in result.task_results[0].feedback

    @pytest.mark.asyncio
    @patch("services.verification.pull_request._fetch_pr_diff", autospec=True)
    @patch("services.verification.pull_request._fetch_pr_data", autospec=True)
    async def test_merged_pr_with_indicators_passes(self, mock_data, mock_diff):
        """Merged PR with matching pass indicators passes instantly."""
        mock_data.return_value = {
            "merged": True,
            "state": "closed",
            "head": {"ref": "feature/logging-setup"},
        }
        mock_diff.return_value = (
            "+import logging\n+logging.basicConfig(level=logging.INFO)"
        )
        result = await validate_pr(
            _TEST_PR_URL,
            _make_pr_requirement(pass_indicators=["import logging"]),
        )
        assert result.is_valid
        assert result.task_results
        assert result.task_results[0].passed


@pytest.mark.unit
class TestValidatePrErrorHandling:
    """Tests for GitHub API error handling."""

    @pytest.mark.asyncio
    @patch("services.verification.pull_request._fetch_pr_data", autospec=True)
    async def test_pr_not_found_404(self, mock_fetch):
        response = httpx.Response(404, request=httpx.Request("GET", "https://test"))
        mock_fetch.side_effect = httpx.HTTPStatusError(
            "Not Found", request=response.request, response=response
        )
        result = await validate_pr(_TEST_PR_URL, _make_pr_requirement())
        assert not result.is_valid
        assert "not found" in result.message.lower()
        assert result.verification_completed is True

    @pytest.mark.asyncio
    @patch("services.verification.pull_request._fetch_pr_data", autospec=True)
    async def test_github_server_error_marks_server_error(self, mock_fetch):
        response = httpx.Response(500, request=httpx.Request("GET", "https://test"))
        mock_fetch.side_effect = httpx.HTTPStatusError(
            "Server Error", request=response.request, response=response
        )
        result = await validate_pr(_TEST_PR_URL, _make_pr_requirement())
        assert not result.is_valid
        assert result.verification_completed is False
