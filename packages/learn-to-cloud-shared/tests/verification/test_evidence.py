"""Tests for the evidence collector split (cap + per-source getters)."""

from unittest.mock import AsyncMock

import httpx
import pytest

from learn_to_cloud_shared.verification import repo_files as repo_files_module
from learn_to_cloud_shared.verification.evidence import (
    EvidenceError,
    apply_evidence_cap,
    collect_repo_file_evidence,
    collect_submitted_text_evidence,
)
from learn_to_cloud_shared.verification.github_errors import GitHubServerError
from learn_to_cloud_shared.verification.repo_files import (
    GitHubRepoFiles,
)
from learn_to_cloud_shared.verification.tasks.base import (
    EvidencePolicy,
    LLMRubricGraderConfig,
    VerificationTask,
)
from tests.fakes.repo_files import InMemoryRepoFiles


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
            optional_files=[
                "a",
                "b",
                "c",
                "a.txt",
                "b.txt",
                "big.txt",
                "submission.txt",
                "present.txt",
                "second.txt",
            ],
            max_files=max_files,
            max_file_size_bytes=max_file_size_bytes,
            max_total_bytes=max_total_bytes,
        ),
        grader=LLMRubricGraderConfig(
            rubric_id="test", prompt_version="test", passing_score=0.5
        ),
    )


def test_apply_evidence_cap_rejects_duplicate_paths():
    with pytest.raises(EvidenceError, match="evidence.selection"):
        apply_evidence_cap(
            _task(),
            [("a.txt", "one"), ("a.txt", "two"), ("b.txt", "three")],
        )


def test_apply_evidence_cap_limits_file_count():
    with pytest.raises(EvidenceError, match="evidence.file_limit"):
        apply_evidence_cap(
            _task(max_files=2),
            [("a", "1"), ("b", "2"), ("c", "3")],
        )


def test_apply_evidence_cap_rejects_large_file():
    with pytest.raises(EvidenceError, match="evidence.item_limit"):
        apply_evidence_cap(_task(max_file_size_bytes=100), [("big.txt", "x" * 500)])


def test_apply_evidence_cap_stops_at_total_budget():
    with pytest.raises(EvidenceError, match="evidence.total_limit"):
        apply_evidence_cap(
            _task(max_total_bytes=10),
            [("a", "xxxxx"), ("b", "yyyyy"), ("c", "zzzzz")],
        )


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
async def test_collect_repo_file_evidence_checks_selected_count_before_reading():
    repo_files = InMemoryRepoFiles({"present.txt": "here", "second.txt": "also"})
    with pytest.raises(EvidenceError, match="evidence.file_limit"):
        await collect_repo_file_evidence(
            repo_files,
            "owner",
            "repo",
            ["present.txt", "missing.txt", "second.txt"],
            _task(max_files=1),
        )


@pytest.mark.asyncio
@pytest.mark.parametrize("failure", [401, 403, 429, 503, "network"])
async def test_failed_later_file_never_returns_partial_evidence(monkeypatch, failure):
    requested_paths = []

    def respond(request):
        if request.url.host == "api.github.com":
            return httpx.Response(
                200,
                json={"tree": [{"type": "blob", "path": p} for p in ["a", "b", "c"]]},
            )
        requested_paths.append(request.url.path.rsplit("/", 1)[-1])
        if len(requested_paths) == 1:
            return httpx.Response(200, text="successfully fetched first file")
        if failure == "network":
            raise httpx.ReadTimeout("private connection details", request=request)
        return httpx.Response(failure, text="private provider response")

    async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as client:
        monkeypatch.setattr(
            repo_files_module, "get_github_client", AsyncMock(return_value=client)
        )
        # Tree discovery uses the API helper's own client reference.
        monkeypatch.setattr(
            "learn_to_cloud_shared.verification.github_http._get_github_client",
            AsyncMock(return_value=client),
        )
        expected = (
            httpx.ReadTimeout
            if failure == "network"
            else GitHubServerError
            if failure in (429, 503)
            else httpx.HTTPStatusError
        )
        with pytest.raises(expected):
            await collect_repo_file_evidence(
                GitHubRepoFiles(), "owner", "repo", ["a", "b", "c"], _task()
            )

    assert requested_paths == ["a", "b"]


@pytest.mark.asyncio
async def test_disappearing_file_never_returns_partial_evidence():
    files = InMemoryRepoFiles({"a": "first", "c": "third"}, tree=["a", "b", "c"])
    task = _task()
    with pytest.raises(EvidenceError, match="evidence.changed"):
        await collect_repo_file_evidence(
            files,
            "owner",
            "repo",
            ["a", "b", "c"],
            task,
        )
