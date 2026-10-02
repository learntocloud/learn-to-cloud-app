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

These tests inject the in-memory GitHub seam instead of patching internals, so
they exercise the real ``verify_codeql_status`` logic through the seam.
"""

import httpx2
import pytest

from learn_to_cloud.verification.codeql_status import verify_codeql_status
from learn_to_cloud.verification.github_errors import GitHubServerError
from tests.support.fakes.github import FakeGitHub

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


def _http_error(status: int) -> httpx2.HTTPStatusError:
    response = httpx2.Response(status, request=httpx2.Request("GET", "https://test"))
    return httpx2.HTTPStatusError("err", request=response.request, response=response)


@pytest.mark.unit
class TestCodeQLStatusCheck:
    """Tests for the CodeQL workflow-run + HEAD-anchoring gate."""

    async def test_workflow_not_found_returns_advanced_setup_message(self):
        github = FakeGitHub(run_error=_http_error(404), sha=_HEAD)
        result = await verify_codeql_status(_TEST_OWNER, _TEST_REPO, github)
        assert not result.is_valid
        assert "advanced setup" in result.message.lower()
        assert "codeql.yml" in result.message

    async def test_no_runs_on_main(self):
        github = FakeGitHub(run=None, sha=_HEAD)
        result = await verify_codeql_status(_TEST_OWNER, _TEST_REPO, github)
        assert not result.is_valid
        assert "No CodeQL runs" in result.message

    async def test_run_in_progress(self):
        github = FakeGitHub(run=_run(status="in_progress", conclusion=None), sha=_HEAD)
        result = await verify_codeql_status(_TEST_OWNER, _TEST_REPO, github)
        assert not result.is_valid
        assert "still" in result.message

    async def test_run_succeeded_on_current_head_passes(self):
        # CodeQL alerts do not fail the run; conclusion success is what matters.
        github = FakeGitHub(run=_run(), sha=_HEAD)
        result = await verify_codeql_status(_TEST_OWNER, _TEST_REPO, github)
        assert result.is_valid
        assert "#10" in result.message

    async def test_green_but_stale_head_is_rejected(self):
        github = FakeGitHub(run=_run(head_sha="oldsha000"), sha=_HEAD)
        result = await verify_codeql_status(_TEST_OWNER, _TEST_REPO, github)
        assert not result.is_valid
        assert "latest commit" in result.message.lower()

    async def test_run_failed(self):
        run_url = "https://github.com/testuser/journal-starter/actions/runs/999"
        github = FakeGitHub(
            run=_run(conclusion="failure", run_number=7, html_url=run_url), sha=_HEAD
        )
        result = await verify_codeql_status(_TEST_OWNER, _TEST_REPO, github)
        assert not result.is_valid
        assert "failure" in result.message
        assert run_url in result.message

    async def test_branch_not_found(self):
        github = FakeGitHub(run=_run(), sha_error=_http_error(404))
        result = await verify_codeql_status(_TEST_OWNER, _TEST_REPO, github)
        assert not result.is_valid
        assert "main branch" in result.message

    async def test_missing_head_sha(self):
        github = FakeGitHub(run=_run(), sha=None)
        result = await verify_codeql_status(_TEST_OWNER, _TEST_REPO, github)
        assert not result.is_valid


@pytest.mark.unit
class TestCodeQLStatusErrorHandling:
    """Tests for GitHub API error handling."""

    async def test_runs_server_error(self):
        github = FakeGitHub(
            run_error=GitHubServerError("GitHub returned 500", status_code=500),
            sha=_HEAD,
        )
        result = await verify_codeql_status(_TEST_OWNER, _TEST_REPO, github)
        assert not result.is_valid
        assert result.verification_completed is False

    async def test_ref_transient_failure(self):
        github = FakeGitHub(
            run=_run(), sha_error=httpx2.ConnectError("connection refused")
        )
        result = await verify_codeql_status(_TEST_OWNER, _TEST_REPO, github)
        assert not result.is_valid
        assert result.verification_completed is False
