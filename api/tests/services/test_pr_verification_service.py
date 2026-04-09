"""Tests for pr_verification_service.

Tests cover:
- PR merge state verification
- Error handling for GitHub API failures
- Workflow routing (deterministic vs LLM grading)
"""

from unittest.mock import MagicMock, patch

import httpx
import pytest

from models import SubmissionType
from schemas import HandsOnRequirement
from services.verification.pull_request import validate_pr


def _make_pr_requirement(
    requirement_id: str = "journal-pr-logging",
) -> HandsOnRequirement:
    """Helper to create a PR_REVIEW requirement."""
    return HandsOnRequirement(
        id=requirement_id,
        submission_type=SubmissionType.PR_REVIEW,
        name="Test PR Requirement",
        description="Test",
        placeholder="https://github.com/user/repo/pull/1",
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
    @patch("services.verification.pull_request._fetch_pr_data", autospec=True)
    async def test_merged_pr_passes(self, mock_data):
        mock_data.return_value = {
            "merged": True,
            "state": "closed",
            "head": {"ref": "feature/logging-setup"},
        }
        result = await validate_pr(_TEST_PR_URL, _make_pr_requirement())
        assert result.is_valid
        assert "verified" in result.message.lower()
        assert "feature/logging-setup" in result.message


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
        assert result.server_error is not True

    @pytest.mark.asyncio
    @patch("services.verification.pull_request._fetch_pr_data", autospec=True)
    async def test_github_server_error_marks_server_error(self, mock_fetch):
        response = httpx.Response(500, request=httpx.Request("GET", "https://test"))
        mock_fetch.side_effect = httpx.HTTPStatusError(
            "Server Error", request=response.request, response=response
        )
        result = await validate_pr(_TEST_PR_URL, _make_pr_requirement())
        assert not result.is_valid
        assert result.server_error is True


# =============================================================================
# Deterministic-only vs. workflow routing
# =============================================================================


@pytest.mark.unit
class TestValidatePrRouting:
    """Tests for workflow vs deterministic-only routing."""

    @pytest.mark.asyncio
    @patch("services.verification.pull_request._fetch_pr_data", autospec=True)
    async def test_no_grading_criteria_uses_deterministic_only(self, mock_data):
        """Without grading_criteria, validate_pr uses deterministic path only."""
        mock_data.return_value = {
            "merged": True,
            "state": "closed",
            "head": {"ref": "feature/test"},
        }
        result = await validate_pr(_TEST_PR_URL, _make_pr_requirement())
        assert result.is_valid
        assert "verified" in result.message.lower()

    @pytest.mark.asyncio
    @patch("services.verification.pull_request.get_llm_chat_client", autospec=True)
    @patch("services.verification.pull_request._fetch_pr_data", autospec=True)
    async def test_grading_criteria_triggers_workflow(self, mock_data, mock_llm_client):
        """With grading_criteria, validate_pr initializes the LLM grader."""
        mock_data.return_value = {
            "merged": True,
            "state": "closed",
            "head": {"ref": "feature/test"},
            "title": "Test",
        }
        # LLM client will be called to build the grader Agent
        mock_llm_client.return_value = MagicMock()
        requirement = HandsOnRequirement(
            id="journal-pr-logging",
            submission_type=SubmissionType.PR_REVIEW,
            name="PR: Logging Setup",
            description="Test",
            expected_files=["api/main.py"],
            grading_criteria=["MUST have import logging"],
            pass_indicators=["import logging"],
            fail_indicators=["# TODO"],
        )
        # The workflow will fail because the mock LLM client can't
        # actually run, but we just need to verify it was invoked
        await validate_pr(_TEST_PR_URL, requirement)
        mock_llm_client.assert_called_once()
