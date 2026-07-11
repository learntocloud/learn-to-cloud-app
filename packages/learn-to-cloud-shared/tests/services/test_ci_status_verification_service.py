"""Tests for CI status verification service.

Tests cover:
- CI workflow not found (404)
- No runs on main
- Run still in progress
- Run succeeded
- Run failed
- GitHub API errors

URL validation and ownership checks are exercised by the engine gate tests.

These tests inject an :class:`InMemoryWorkflowRuns` adapter instead of
patching internals, so they exercise the real ``verify_ci_status`` logic
through the ``WorkflowRuns`` seam.
"""

import httpx
import pytest

from learn_to_cloud_shared.verification.ci_status import verify_ci_status
from learn_to_cloud_shared.verification.errors import GitHubServerError
from learn_to_cloud_shared.verification.workflow_runs import InMemoryWorkflowRuns

_TEST_OWNER = "testuser"
_TEST_REPO = "journal-starter"


# =============================================================================
# CI Workflow Status
# =============================================================================


@pytest.mark.unit
class TestCiStatusCheck:
    """Tests for the GitHub Actions workflow status check."""

    async def test_workflow_not_found_returns_helpful_message(self):
        response = httpx.Response(404, request=httpx.Request("GET", "https://test"))
        runs = InMemoryWorkflowRuns(
            error=httpx.HTTPStatusError(
                "Not Found", request=response.request, response=response
            )
        )
        result = await verify_ci_status(_TEST_OWNER, _TEST_REPO, runs)
        assert not result.is_valid
        assert "CI workflow not found" in result.message
        assert "ci.yml" in result.message

    async def test_no_runs_on_main(self):
        runs = InMemoryWorkflowRuns(run=None)
        result = await verify_ci_status(_TEST_OWNER, _TEST_REPO, runs)
        assert not result.is_valid
        assert "No CI runs found" in result.message

    async def test_run_in_progress(self):
        runs = InMemoryWorkflowRuns(
            {
                "status": "in_progress",
                "conclusion": None,
                "run_number": 5,
                "html_url": "https://github.com/testuser/journal-starter/actions/runs/123",
            }
        )
        result = await verify_ci_status(_TEST_OWNER, _TEST_REPO, runs)
        assert not result.is_valid
        assert "still" in result.message
        assert "#5" in result.message

    async def test_run_queued(self):
        runs = InMemoryWorkflowRuns(
            {
                "status": "queued",
                "conclusion": None,
                "run_number": 3,
                "html_url": "https://github.com/testuser/journal-starter/actions/runs/456",
            }
        )
        result = await verify_ci_status(_TEST_OWNER, _TEST_REPO, runs)
        assert not result.is_valid
        assert "#3" in result.message

    async def test_run_succeeded(self):
        runs = InMemoryWorkflowRuns(
            {
                "status": "completed",
                "conclusion": "success",
                "run_number": 10,
                "html_url": "https://github.com/testuser/journal-starter/actions/runs/789",
            }
        )
        result = await verify_ci_status(_TEST_OWNER, _TEST_REPO, runs)
        assert result.is_valid
        assert "#10" in result.message
        assert "passing" in result.message.lower()

    async def test_run_failed(self):
        run_url = "https://github.com/testuser/journal-starter/actions/runs/999"
        runs = InMemoryWorkflowRuns(
            {
                "status": "completed",
                "conclusion": "failure",
                "run_number": 7,
                "html_url": run_url,
            }
        )
        result = await verify_ci_status(_TEST_OWNER, _TEST_REPO, runs)
        assert not result.is_valid
        assert "failure" in result.message
        assert run_url in result.message

    async def test_run_cancelled(self):
        runs = InMemoryWorkflowRuns(
            {
                "status": "completed",
                "conclusion": "cancelled",
                "run_number": 4,
                "html_url": "https://github.com/testuser/journal-starter/actions/runs/111",
            }
        )
        result = await verify_ci_status(_TEST_OWNER, _TEST_REPO, runs)
        assert not result.is_valid
        assert "cancelled" in result.message


# =============================================================================
# GitHub API Error Handling
# =============================================================================


@pytest.mark.unit
class TestCiStatusErrorHandling:
    """Tests for GitHub API error handling."""

    async def test_github_server_error(self):
        runs = InMemoryWorkflowRuns(error=GitHubServerError("GitHub returned 500"))
        result = await verify_ci_status(_TEST_OWNER, _TEST_REPO, runs)
        assert not result.is_valid
        assert result.verification_completed is False

    async def test_transient_failure(self):
        runs = InMemoryWorkflowRuns(error=httpx.ConnectError("connection refused"))
        result = await verify_ci_status(_TEST_OWNER, _TEST_REPO, runs)
        assert not result.is_valid
        assert result.verification_completed is False

    async def test_request_timeout(self):
        runs = InMemoryWorkflowRuns(error=httpx.TimeoutException("timed out"))
        result = await verify_ci_status(_TEST_OWNER, _TEST_REPO, runs)
        assert not result.is_valid
        assert result.verification_completed is False
