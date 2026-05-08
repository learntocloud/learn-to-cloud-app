"""Journal API repository evidence collection for final rubric grading."""

from __future__ import annotations

from learn_to_cloud_shared.verification.evidence import collect_repo_file_evidence
from learn_to_cloud_shared.verification.tasks.base import (
    EvidenceBundle,
    VerificationTask,
)
from learn_to_cloud_shared.verification.tasks.phase3 import (
    JOURNAL_API_FINAL_RUBRIC_TASK,
    JOURNAL_API_IMPORTANT_PATHS,
)

_PYTHON_TEST_SUFFIX = ".py"
_WORKFLOW_SUFFIXES = (".yml", ".yaml")


async def collect_journal_api_implementation_evidence(
    owner: str,
    repo: str,
    file_paths: list[str],
    task: VerificationTask = JOURNAL_API_FINAL_RUBRIC_TASK,
) -> EvidenceBundle:
    """Collect bounded Phase 3 Journal API evidence for rubric grading."""
    paths = _select_journal_api_evidence_paths(file_paths, task)
    return await collect_repo_file_evidence(owner, repo, paths, task)


def _select_journal_api_evidence_paths(
    file_paths: list[str],
    task: VerificationTask,
) -> list[str]:
    exact_matches = [path for path in JOURNAL_API_IMPORTANT_PATHS if path in file_paths]
    test_candidates = [
        path
        for path in file_paths
        if path.startswith("tests/") and path.endswith(_PYTHON_TEST_SUFFIX)
    ]
    workflow_candidates = [
        path
        for path in file_paths
        if path.startswith(".github/workflows/") and path.endswith(_WORKFLOW_SUFFIXES)
    ]
    selected = [*exact_matches, *test_candidates, *workflow_candidates]
    return list(dict.fromkeys(selected))[: task.evidence.max_files]
