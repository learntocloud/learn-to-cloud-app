"""Tests for CI status verification service.

Tests cover:
- Repo URL validation and ownership checks
- CI workflow not found (404)
- No runs on main
- Run still in progress
- Run succeeded
- Run failed
- GitHub API errors
"""

from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest
from circuitbreaker import CircuitBreakerError

from services.verification.ci_status import verify_ci_status

_TEST_REPO_URL = "https://github.com/testuser/journal-starter"
_TEST_USERNAME = "testuser"


def _make_response(json_data: dict, status_code: int = 200) -> httpx.Response:
    """Create an httpx.Response with JSON body."""
    response = MagicMock(spec=httpx.Response)
    response.status_code = status_code
    response.json.return_value = json_data
    return response


# =============================================================================
# URL Validation
# =============================================================================


@pytest.mark.unit
class TestUrlValidation:
    """Tests for repo URL parsing and ownership checks."""

    async def test_invalid_url_fails(self):
        result = await verify_ci_status("not-a-url", _TEST_USERNAME)
        assert not result.is_valid

    async def test_wrong_owner_fails(self):
        result = await verify_ci_status(
            "https://github.com/otheruser/journal-starter", _TEST_USERNAME
        )
        assert not result.is_valid
        assert "does not match" in result.message

    async def test_wrong_repo_name_fails(self):
        result = await verify_ci_status(
            _TEST_REPO_URL, _TEST_USERNAME, expected_repo_name="other-repo"
        )
        assert not result.is_valid
        assert "does not match" in result.message


# =============================================================================
# CI Workflow Status
# =============================================================================


@pytest.mark.unit
class TestCiStatusCheck:
    """Tests for the GitHub Actions workflow status check."""

    @patch("services.verification.ci_status.github_api_get", autospec=True)
    async def test_workflow_not_found_returns_helpful_message(self, mock_get):
        response = httpx.Response(404, request=httpx.Request("GET", "https://test"))
        mock_get.side_effect = httpx.HTTPStatusError(
            "Not Found", request=response.request, response=response
        )
        result = await verify_ci_status(_TEST_REPO_URL, _TEST_USERNAME)
        assert not result.is_valid
        assert "CI workflow not found" in result.message
        assert "ci.yml" in result.message

    @patch("services.verification.ci_status.github_api_get", autospec=True)
    async def test_no_runs_on_main(self, mock_get):
        mock_get.return_value = _make_response({"workflow_runs": []})
        result = await verify_ci_status(_TEST_REPO_URL, _TEST_USERNAME)
        assert not result.is_valid
        assert "No CI runs found" in result.message

    @patch("services.verification.ci_status.github_api_get", autospec=True)
    async def test_run_in_progress(self, mock_get):
        mock_get.return_value = _make_response(
            {
                "workflow_runs": [
                    {
                        "status": "in_progress",
                        "conclusion": None,
                        "run_number": 5,
                        "html_url": "https://github.com/testuser/journal-starter/actions/runs/123",
                    }
                ]
            }
        )
        result = await verify_ci_status(_TEST_REPO_URL, _TEST_USERNAME)
        assert not result.is_valid
        assert "still" in result.message
        assert "#5" in result.message

    @patch("services.verification.ci_status.github_api_get", autospec=True)
    async def test_run_queued(self, mock_get):
        mock_get.return_value = _make_response(
            {
                "workflow_runs": [
                    {
                        "status": "queued",
                        "conclusion": None,
                        "run_number": 3,
                        "html_url": "https://github.com/testuser/journal-starter/actions/runs/456",
                    }
                ]
            }
        )
        result = await verify_ci_status(_TEST_REPO_URL, _TEST_USERNAME)
        assert not result.is_valid
        assert "#3" in result.message

    @patch("services.verification.ci_status.github_api_get", autospec=True)
    async def test_run_succeeded(self, mock_get):
        mock_get.return_value = _make_response(
            {
                "workflow_runs": [
                    {
                        "status": "completed",
                        "conclusion": "success",
                        "run_number": 10,
                        "html_url": "https://github.com/testuser/journal-starter/actions/runs/789",
                    }
                ]
            }
        )
        result = await verify_ci_status(_TEST_REPO_URL, _TEST_USERNAME)
        assert result.is_valid
        assert "#10" in result.message
        assert "passing" in result.message.lower()

    @patch("services.verification.ci_status.github_api_get", autospec=True)
    async def test_run_failed(self, mock_get):
        run_url = "https://github.com/testuser/journal-starter/actions/runs/999"
        mock_get.return_value = _make_response(
            {
                "workflow_runs": [
                    {
                        "status": "completed",
                        "conclusion": "failure",
                        "run_number": 7,
                        "html_url": run_url,
                    }
                ]
            }
        )
        result = await verify_ci_status(_TEST_REPO_URL, _TEST_USERNAME)
        assert not result.is_valid
        assert "failure" in result.message
        assert run_url in result.message

    @patch("services.verification.ci_status.github_api_get", autospec=True)
    async def test_run_cancelled(self, mock_get):
        mock_get.return_value = _make_response(
            {
                "workflow_runs": [
                    {
                        "status": "completed",
                        "conclusion": "cancelled",
                        "run_number": 4,
                        "html_url": "https://github.com/testuser/journal-starter/actions/runs/111",
                    }
                ]
            }
        )
        result = await verify_ci_status(_TEST_REPO_URL, _TEST_USERNAME)
        assert not result.is_valid
        assert "cancelled" in result.message


# =============================================================================
# GitHub API Error Handling
# =============================================================================


@pytest.mark.unit
class TestCiStatusErrorHandling:
    """Tests for GitHub API error handling."""

    @patch("services.verification.ci_status.github_api_get", autospec=True)
    async def test_github_server_error(self, mock_get):
        response = httpx.Response(500, request=httpx.Request("GET", "https://test"))
        mock_get.side_effect = httpx.HTTPStatusError(
            "Server Error", request=response.request, response=response
        )
        result = await verify_ci_status(_TEST_REPO_URL, _TEST_USERNAME)
        assert not result.is_valid
        assert result.server_error is True

    @patch("services.verification.ci_status.github_api_get", autospec=True)
    async def test_circuit_breaker_open(self, mock_get):
        mock_get.side_effect = CircuitBreakerError(AsyncMock())
        result = await verify_ci_status(_TEST_REPO_URL, _TEST_USERNAME)
        assert not result.is_valid
        assert result.server_error is True

    @patch("services.verification.ci_status.github_api_get", autospec=True)
    async def test_request_timeout(self, mock_get):
        mock_get.side_effect = httpx.TimeoutException("timed out")
        result = await verify_ci_status(_TEST_REPO_URL, _TEST_USERNAME)
        assert not result.is_valid
        assert result.server_error is True

    @patch("services.verification.ci_status.github_api_get", autospec=True)
    async def test_expected_repo_name_enforced(self, mock_get):
        mock_get.return_value = _make_response(
            {
                "workflow_runs": [
                    {
                        "status": "completed",
                        "conclusion": "success",
                        "run_number": 1,
                        "html_url": "https://github.com/testuser/journal-starter/actions/runs/1",
                    }
                ]
            }
        )
        result = await verify_ci_status(
            _TEST_REPO_URL,
            _TEST_USERNAME,
            expected_repo_name="journal-starter",
        )
        assert result.is_valid

        result = await verify_ci_status(
            _TEST_REPO_URL,
            _TEST_USERNAME,
            expected_repo_name="wrong-name",
        )
        assert not result.is_valid
