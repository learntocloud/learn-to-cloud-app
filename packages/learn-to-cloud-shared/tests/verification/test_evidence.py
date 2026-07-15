"""Tests for the evidence collector split (cap + per-source getters)."""

import pytest

from learn_to_cloud_shared.verification.evidence import (
    apply_evidence_cap,
    collect_repo_file_evidence,
    collect_submitted_text_evidence,
)
from learn_to_cloud_shared.verification.repo_files import InMemoryRepoFiles
from learn_to_cloud_shared.verification.tasks.base import (
    EvidencePolicy,
    FilePresenceGraderConfig,
    VerificationTask,
)


def _task(
    *,
    source: str = "repo_files",
    max_files: int = 10,
    max_file_size_bytes: int = 50 * 1024,
    max_total_bytes: int = 200 * 1024,
) -> VerificationTask:
    return VerificationTask(
        id="task-1",
        phase_id=3,
        name="Test task",
        evidence=EvidencePolicy(
            source=source,
            max_files=max_files,
            max_file_size_bytes=max_file_size_bytes,
            max_total_bytes=max_total_bytes,
        ),
        grader=FilePresenceGraderConfig(),
    )


def test_apply_evidence_cap_deduplicates_paths():
    bundle = apply_evidence_cap(
        _task(),
        [("a.txt", "one"), ("a.txt", "two"), ("b.txt", "three")],
    )
    assert [item.path for item in bundle.items] == ["a.txt", "b.txt"]
    assert bundle.items[0].content == "one"


def test_apply_evidence_cap_limits_file_count():
    bundle = apply_evidence_cap(
        _task(max_files=2),
        [("a", "1"), ("b", "2"), ("c", "3")],
    )
    assert [item.path for item in bundle.items] == ["a", "b"]


def test_apply_evidence_cap_truncates_large_file():
    bundle = apply_evidence_cap(
        _task(max_file_size_bytes=100),
        [("big.txt", "x" * 500)],
    )
    assert bundle.items[0].truncated is True
    assert len(bundle.items[0].content.encode("utf-8")) <= 100


def test_apply_evidence_cap_stops_at_total_budget():
    bundle = apply_evidence_cap(
        _task(max_total_bytes=10),
        [("a", "xxxxx"), ("b", "yyyyy"), ("c", "zzzzz")],
    )
    assert [item.path for item in bundle.items] == ["a", "b"]
    assert bundle.total_bytes == 10


def test_apply_evidence_cap_sets_source_and_task_id():
    bundle = apply_evidence_cap(_task(source="submitted_text"), [("a", "1")])
    assert bundle.task_id == "task-1"
    assert bundle.source == "submitted_text"


def test_collect_submitted_text_evidence_is_passthrough():
    bundle = collect_submitted_text_evidence(_task(source="submitted_text"), "hello")
    assert bundle.source == "submitted_text"
    assert bundle.items[0].content == "hello"
    assert bundle.items[0].path == "submission.txt"


@pytest.mark.asyncio
async def test_collect_repo_file_evidence_skips_missing_and_caps():
    repo_files = InMemoryRepoFiles({"present.txt": "here", "second.txt": "also"})
    bundle = await collect_repo_file_evidence(
        repo_files,
        "owner",
        "repo",
        ["present.txt", "missing.txt", "second.txt"],
        _task(max_files=1),
    )
    assert [item.path for item in bundle.items] == ["present.txt"]
    assert bundle.source == "repo_files"
