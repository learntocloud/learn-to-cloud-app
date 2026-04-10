"""Tests for pr_verification_service.

Tests cover:
- PR merge state verification
- Error handling for GitHub API failures
- Workflow routing (deterministic vs LLM grading)
"""

import contextlib
from unittest.mock import AsyncMock, MagicMock, patch

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
        grading_criteria=["MUST have meaningful changes"],
    )


_TEST_PR_URL = "https://github.com/testuser/journal-starter/pull/1"


# =============================================================================
# Validation Tests
# =============================================================================


@pytest.mark.unit
class TestValidatePr:
    """Tests for the full PR validation flow."""

    @pytest.mark.asyncio
    @patch(
        "services.verification.pull_request.get_llm_chat_client", new_callable=AsyncMock
    )
    @patch("services.verification.pull_request._fetch_pr_data", autospec=True)
    async def test_open_pr_fails(self, mock_fetch, mock_llm_client):
        mock_fetch.return_value = {"merged": False, "state": "open"}
        mock_llm_client.return_value = MagicMock()
        result = await validate_pr(_TEST_PR_URL, _make_pr_requirement())
        assert not result.is_valid
        assert "still open" in result.message

    @pytest.mark.asyncio
    @patch(
        "services.verification.pull_request.get_llm_chat_client", new_callable=AsyncMock
    )
    @patch("services.verification.pull_request._fetch_pr_data", autospec=True)
    async def test_closed_unmerged_pr_fails(self, mock_fetch, mock_llm_client):
        mock_fetch.return_value = {"merged": False, "state": "closed"}
        mock_llm_client.return_value = MagicMock()
        result = await validate_pr(_TEST_PR_URL, _make_pr_requirement())
        assert not result.is_valid
        assert "without merging" in result.message

    @pytest.mark.asyncio
    @patch(
        "services.verification.pull_request.get_llm_chat_client", new_callable=AsyncMock
    )
    @patch("services.verification.pull_request._fetch_pr_diff", autospec=True)
    @patch("services.verification.pull_request._fetch_pr_data", autospec=True)
    async def test_merged_pr_reaches_grader(
        self, mock_data, mock_diff, mock_llm_client
    ):
        mock_data.return_value = {
            "merged": True,
            "state": "closed",
            "head": {"ref": "feature/logging-setup"},
        }
        mock_diff.return_value = "<pr_diff>\n+import logging\n</pr_diff>"
        mock_llm_client.return_value = MagicMock()
        # The workflow will fail because the mock client can't run an
        # actual agent, but we verify the diff was fetched.
        with contextlib.suppress(Exception):
            await validate_pr(_TEST_PR_URL, _make_pr_requirement())
        mock_diff.assert_called_once()


@pytest.mark.unit
class TestValidatePrErrorHandling:
    """Tests for GitHub API error handling."""

    @pytest.mark.asyncio
    @patch(
        "services.verification.pull_request.get_llm_chat_client", new_callable=AsyncMock
    )
    @patch("services.verification.pull_request._fetch_pr_data", autospec=True)
    async def test_pr_not_found_404(self, mock_fetch, mock_llm_client):
        response = httpx.Response(404, request=httpx.Request("GET", "https://test"))
        mock_fetch.side_effect = httpx.HTTPStatusError(
            "Not Found", request=response.request, response=response
        )
        mock_llm_client.return_value = MagicMock()
        result = await validate_pr(_TEST_PR_URL, _make_pr_requirement())
        assert not result.is_valid
        assert "not found" in result.message.lower()
        assert result.server_error is not True

    @pytest.mark.asyncio
    @patch(
        "services.verification.pull_request.get_llm_chat_client", new_callable=AsyncMock
    )
    @patch("services.verification.pull_request._fetch_pr_data", autospec=True)
    async def test_github_server_error_marks_server_error(
        self, mock_fetch, mock_llm_client
    ):
        response = httpx.Response(500, request=httpx.Request("GET", "https://test"))
        mock_fetch.side_effect = httpx.HTTPStatusError(
            "Server Error", request=response.request, response=response
        )
        mock_llm_client.return_value = MagicMock()
        result = await validate_pr(_TEST_PR_URL, _make_pr_requirement())
        assert not result.is_valid
        assert result.server_error is True


# =============================================================================
# Deterministic-only vs. workflow routing
# =============================================================================


@pytest.mark.unit
class TestValidatePrRouting:
    """Tests for LLM client creation."""

    @pytest.mark.asyncio
    @patch(
        "services.verification.pull_request.get_llm_chat_client", new_callable=AsyncMock
    )
    @patch("services.verification.pull_request._fetch_pr_diff", autospec=True)
    @patch("services.verification.pull_request._fetch_pr_data", autospec=True)
    async def test_llm_client_always_created(
        self, mock_data, mock_diff, mock_llm_client
    ):
        """The Agent is always created as a workflow participant."""
        mock_data.return_value = {
            "merged": True,
            "state": "closed",
            "head": {"ref": "feature/test"},
            "title": "Test",
        }
        mock_diff.return_value = "<pr_diff>\n+import logging\n</pr_diff>"
        mock_llm_client.return_value = MagicMock()
        # The workflow will fail because the mock client can't run an
        # actual agent, but we verify the LLM client was created.
        with contextlib.suppress(Exception):
            await validate_pr(_TEST_PR_URL, _make_pr_requirement())
        mock_llm_client.assert_called_once()
