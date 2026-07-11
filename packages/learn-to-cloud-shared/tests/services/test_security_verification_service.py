"""Tests for security_verification_service (Phase 6).

Covers:
- 404 / not-public repo handling
- Dependabot and CodeQL detection

Evidence is supplied through the ``RepoFiles`` seam with an in-memory
adapter, so these tests exercise the grading rules without the network.

URL validation and ownership checks are exercised by the engine gate tests.
"""

import httpx
import pytest

from learn_to_cloud_shared.verification.repo_files import InMemoryRepoFiles
from learn_to_cloud_shared.verification.security_scanning import (
    validate_security_scanning,
)

_TEST_OWNER = "testuser"
_TEST_REPO = "my-repo"

_VALID_DEPENDABOT = "version: 2\nupdates:\n  - package-ecosystem: pip\n"
_CODEQL_WORKFLOW = (
    "name: CodeQL\non: [push]\njobs:\n  analyze:\n    steps:\n"
    "      - uses: github/codeql-action/analyze@v3\n"
)


# ---------------------------------------------------------------------------
# 404 / not-public repo
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestValidateSecurityScanning404:
    """Repo-not-found handling."""

    @pytest.mark.asyncio
    async def test_404_returns_not_found(self):
        mock_response = httpx.Response(
            status_code=404, request=httpx.Request("GET", "https://api.github.com")
        )
        repo_files = InMemoryRepoFiles(
            tree_error=httpx.HTTPStatusError(
                "Not Found", request=mock_response.request, response=mock_response
            )
        )
        result = await validate_security_scanning(
            _TEST_OWNER, _TEST_REPO, repo_files=repo_files
        )
        assert result.is_valid is False
        assert "not found" in result.message.lower()
        assert result.username_match is True


# ---------------------------------------------------------------------------
# Dependabot and CodeQL detection
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestValidateSecurityScanningDetection:
    """Detection of security scanning configuration."""

    @pytest.mark.asyncio
    async def test_dependabot_only_passes(self):
        repo_files = InMemoryRepoFiles({".github/dependabot.yml": _VALID_DEPENDABOT})
        result = await validate_security_scanning(
            _TEST_OWNER, _TEST_REPO, repo_files=repo_files
        )
        assert result.is_valid is True

    @pytest.mark.asyncio
    async def test_codeql_only_passes(self):
        repo_files = InMemoryRepoFiles(
            {".github/workflows/codeql.yml": _CODEQL_WORKFLOW}
        )
        result = await validate_security_scanning(
            _TEST_OWNER, _TEST_REPO, repo_files=repo_files
        )
        assert result.is_valid is True

    @pytest.mark.asyncio
    async def test_no_scanning_fails(self):
        repo_files = InMemoryRepoFiles({"README.md": "# project\n"})
        result = await validate_security_scanning(
            _TEST_OWNER, _TEST_REPO, repo_files=repo_files
        )
        assert result.is_valid is False
        assert result.task_results is not None
        assert all(not t.passed for t in result.task_results)
