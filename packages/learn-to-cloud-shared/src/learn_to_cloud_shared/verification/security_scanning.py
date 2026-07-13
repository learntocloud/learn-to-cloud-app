"""Security scanning evidence collection (Phase 6).

Phase 6 verification is split into two steps (see ``engine.py``):

  * a deterministic gate (``codeql_status``) that proves CodeQL ran green on
    the current ``main`` HEAD, and
  * an LLM rubric review that grades the committed workflow's *quality* and
    confirms it targets Python.

This module supplies the evidence for the review step: it fetches the fixed
CodeQL workflow file plus any Dependabot config from the default branch. The
old file-presence verdict logic is gone; the gate is the source of truth for
"did scanning run and pass".
"""

from __future__ import annotations

from learn_to_cloud_shared.verification.evidence import (
    collect_repo_file_evidence,
)
from learn_to_cloud_shared.verification.repo_files import RepoFiles, default_repo_files
from learn_to_cloud_shared.verification.tasks.base import (
    EvidenceBundle,
    VerificationTask,
)
from learn_to_cloud_shared.verification.tasks.phase6 import (
    CODEQL_WORKFLOW_PATH,
    DEPENDABOT_CONFIG_PATHS,
    SECURITY_SCANNING_RUBRIC_TASK,
)

# Fixed paths graded by the rubric: the committed CodeQL workflow plus optional
# Dependabot config. Missing files are skipped by ``collect_repo_file_evidence``.
SECURITY_SCANNING_EVIDENCE_PATHS = [CODEQL_WORKFLOW_PATH, *DEPENDABOT_CONFIG_PATHS]


async def collect_security_scanning_evidence(
    owner: str,
    repo: str,
    task: VerificationTask = SECURITY_SCANNING_RUBRIC_TASK,
    repo_files: RepoFiles | None = None,
) -> EvidenceBundle:
    """Collect bounded Phase 6 repository evidence for rubric grading.

    Fetches the fixed CodeQL workflow (``.github/workflows/codeql.yml``) and
    any Dependabot config from the default branch. Files that do not exist are
    skipped, so a repo without Dependabot simply yields the workflow alone.
    """
    repo_files = repo_files or default_repo_files()
    return await collect_repo_file_evidence(
        repo_files, owner, repo, SECURITY_SCANNING_EVIDENCE_PATHS, task
    )
