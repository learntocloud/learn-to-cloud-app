"""Tests for Phase 6 security-scanning evidence collection.

The deterministic verdict now lives in the ``codeql_status`` gate (see
``test_codeql_status.py``). This module only covers the evidence bundle the
LLM rubric grades: it gathers the committed CodeQL workflow plus any
Dependabot config from fixed paths, tolerating missing files.

Evidence is supplied through the ``RepoFiles`` seam with an in-memory adapter,
so these tests run without the network.
"""

import pytest

from learn_to_cloud_shared.verification.repo_files import InMemoryRepoFiles
from learn_to_cloud_shared.verification.security_scanning import (
    collect_security_scanning_evidence,
)
from learn_to_cloud_shared.verification.tasks.phase6 import (
    CODEQL_WORKFLOW_PATH,
    SECURITY_SCANNING_RUBRIC_TASK,
)

_TEST_OWNER = "testuser"
_TEST_REPO = "my-repo"

_VALID_DEPENDABOT = "version: 2\nupdates:\n  - package-ecosystem: pip\n"
_CODEQL_WORKFLOW = (
    "name: CodeQL\non: [push]\njobs:\n  analyze:\n    steps:\n"
    "      - uses: github/codeql-action/analyze@v3\n"
)


@pytest.mark.unit
class TestCollectSecurityScanningEvidence:
    """Evidence collection over the fixed Phase 6 paths."""

    async def test_collects_codeql_and_dependabot(self):
        repo_files = InMemoryRepoFiles(
            {
                CODEQL_WORKFLOW_PATH: _CODEQL_WORKFLOW,
                ".github/dependabot.yml": _VALID_DEPENDABOT,
            }
        )
        bundle = await collect_security_scanning_evidence(
            _TEST_OWNER, _TEST_REPO, repo_files=repo_files
        )
        paths = {item.path for item in bundle.items}
        assert CODEQL_WORKFLOW_PATH in paths
        assert ".github/dependabot.yml" in paths
        assert bundle.task_id == SECURITY_SCANNING_RUBRIC_TASK.id

    async def test_missing_dependabot_is_skipped(self):
        repo_files = InMemoryRepoFiles({CODEQL_WORKFLOW_PATH: _CODEQL_WORKFLOW})
        bundle = await collect_security_scanning_evidence(
            _TEST_OWNER, _TEST_REPO, repo_files=repo_files
        )
        paths = {item.path for item in bundle.items}
        assert paths == {CODEQL_WORKFLOW_PATH}

    async def test_empty_repo_yields_no_items(self):
        repo_files = InMemoryRepoFiles({"README.md": "# project\n"})
        bundle = await collect_security_scanning_evidence(
            _TEST_OWNER, _TEST_REPO, repo_files=repo_files
        )
        assert bundle.items == []
