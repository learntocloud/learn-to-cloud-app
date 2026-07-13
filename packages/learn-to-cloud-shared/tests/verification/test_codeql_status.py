"""Tests for CodeQL status verification service (Phase 6).

Tests cover:
- CodeQL workflow not found (404 → advanced-setup message)
- No runs on main
- Run still in progress
- Run succeeded on current HEAD (pass)
- Run succeeded but at an older commit (stale HEAD → fail, wait & retry)
- Run failed
- Successful run with open findings still passes
- Branch head lookup 404 / API errors

URL validation and ownership checks are exercised by the engine gate tests.

These tests inject :class:`InMemoryWorkflowRuns` and :class:`InMemoryRepoRef`
adapters instead of patching internals, so they exercise the real
``verify_codeql_status`` logic through the seams.
"""

import httpx
import pytest

from learn_to_cloud_shared.verification.codeql_status import verify_codeql_status
from learn_to_cloud_shared.verification.errors import GitHubServerError
from learn_to_cloud_shared.verification.repo_ref import InMemoryRepoRef
from learn_to_cloud_shared.verification.workflow_runs import InMemoryWorkflowRuns

_TEST_OWNER = "testuser"
_TEST_REPO = "journal-starter"
_HEAD = "abc123def456"


def _run(**overrides):
    run = {
        "status": "completed",
        "conclusion": "success",
        "head_sha": _HEAD,
        "run_number": 10,
        "html_url": "https://github.com/testuser/journal-starter/actions/runs/789",
    }
    run.update(overrides)
    return run


def _http_error(status: int) -> httpx.HTTPStatusError:
    response = httpx.Response(status, request=httpx.Request("GET", "https://test"))
    return httpx.HTTPStatusError("err", request=response.request, response=response)


@pytest.mark.unit
class TestCodeQLStatusCheck:
    """Tests for the CodeQL workflow-run + HEAD-anchoring gate."""

    async def test_workflow_not_found_returns_advanced_setup_message(self):
        runs = InMemoryWorkflowRuns(error=_http_error(404))
        result = await verify_codeql_status(
            _TEST_OWNER, _TEST_REPO, runs, InMemoryRepoRef(_HEAD)
        )
        assert not result.is_valid
        assert "advanced setup" in result.message.lower()
        assert "codeql.yml" in result.message

    async def test_no_runs_on_main(self):
        runs = InMemoryWorkflowRuns(run=None)
        result = await verify_codeql_status(
            _TEST_OWNER, _TEST_REPO, runs, InMemoryRepoRef(_HEAD)
        )
        assert not result.is_valid
        assert "No CodeQL runs" in result.message

    async def test_run_in_progress(self):
        runs = InMemoryWorkflowRuns(_run(status="in_progress", conclusion=None))
        result = await verify_codeql_status(
            _TEST_OWNER, _TEST_REPO, runs, InMemoryRepoRef(_HEAD)
        )
        assert not result.is_valid
        assert "still" in result.message

    async def test_run_succeeded_on_current_head_passes(self):
        runs = InMemoryWorkflowRuns(_run())
        result = await verify_codeql_status(
            _TEST_OWNER, _TEST_REPO, runs, InMemoryRepoRef(_HEAD)
        )
        assert result.is_valid
        assert "#10" in result.message

    async def test_successful_run_with_findings_still_passes(self):
        # CodeQL alerts do not fail the run; conclusion success is what matters.
        runs = InMemoryWorkflowRuns(_run(conclusion="success"))
        result = await verify_codeql_status(
            _TEST_OWNER, _TEST_REPO, runs, InMemoryRepoRef(_HEAD)
        )
        assert result.is_valid

    async def test_green_but_stale_head_is_rejected(self):
        runs = InMemoryWorkflowRuns(_run(head_sha="oldsha000"))
        result = await verify_codeql_status(
            _TEST_OWNER, _TEST_REPO, runs, InMemoryRepoRef(_HEAD)
        )
        assert not result.is_valid
        assert "latest commit" in result.message.lower()

    async def test_run_failed(self):
        run_url = "https://github.com/testuser/journal-starter/actions/runs/999"
        runs = InMemoryWorkflowRuns(
            _run(conclusion="failure", run_number=7, html_url=run_url)
        )
        result = await verify_codeql_status(
            _TEST_OWNER, _TEST_REPO, runs, InMemoryRepoRef(_HEAD)
        )
        assert not result.is_valid
        assert "failure" in result.message
        assert run_url in result.message

    async def test_branch_not_found(self):
        runs = InMemoryWorkflowRuns(_run())
        ref = InMemoryRepoRef(error=_http_error(404))
        result = await verify_codeql_status(_TEST_OWNER, _TEST_REPO, runs, ref)
        assert not result.is_valid
        assert "main branch" in result.message

    async def test_missing_head_sha(self):
        runs = InMemoryWorkflowRuns(_run())
        result = await verify_codeql_status(
            _TEST_OWNER, _TEST_REPO, runs, InMemoryRepoRef(None)
        )
        assert not result.is_valid


@pytest.mark.unit
class TestCodeQLStatusErrorHandling:
    """Tests for GitHub API error handling."""

    async def test_runs_server_error(self):
        runs = InMemoryWorkflowRuns(error=GitHubServerError("GitHub returned 500"))
        result = await verify_codeql_status(
            _TEST_OWNER, _TEST_REPO, runs, InMemoryRepoRef(_HEAD)
        )
        assert not result.is_valid
        assert result.verification_completed is False

    async def test_ref_transient_failure(self):
        runs = InMemoryWorkflowRuns(_run())
        ref = InMemoryRepoRef(error=httpx.ConnectError("connection refused"))
        result = await verify_codeql_status(_TEST_OWNER, _TEST_REPO, runs, ref)
        assert not result.is_valid
        assert result.verification_completed is False
