"""Journal API repository evidence collection for final rubric grading."""

from __future__ import annotations

from learn_to_cloud_shared.verification.evidence import collect_repo_file_evidence
from learn_to_cloud_shared.verification.repo_files import RepoFiles, default_repo_files
from learn_to_cloud_shared.verification.tasks.base import (
    EvidenceBundle,
    VerificationTask,
)
from learn_to_cloud_shared.verification.tasks.phase3 import (
    JOURNAL_API_FINAL_RUBRIC_TASK,
    JOURNAL_API_IMPORTANT_PATHS,
)


async def collect_journal_api_implementation_evidence(
    owner: str,
    repo: str,
    file_paths: list[str],
    task: VerificationTask = JOURNAL_API_FINAL_RUBRIC_TASK,
    repo_files: RepoFiles | None = None,
) -> EvidenceBundle:
    """Collect bounded Phase 3 Journal API evidence for rubric grading."""
    repo_files = repo_files or default_repo_files()
    return await collect_repo_file_evidence(
        repo_files,
        owner,
        repo,
        list(JOURNAL_API_IMPORTANT_PATHS),
        task,
        inventory=file_paths,
    )
