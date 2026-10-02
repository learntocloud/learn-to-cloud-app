"""Tests for the evidence collector split (cap + per-source getters)."""

from unittest.mock import AsyncMock

import httpx2
import pytest

from learn_to_cloud.verification import github_api
from learn_to_cloud.verification.evidence import (
    EvidenceError,
    apply_evidence_cap,
    collect_repo_file_evidence,
)
from learn_to_cloud.verification.github_api import GitHubClient
from learn_to_cloud.verification.github_errors import GitHubServerError
from learn_to_cloud.verification.tasks.base import (
    EvidencePolicy,
    EvidenceSource,
    LLMRubricGraderConfig,
    VerificationTask,
)
from tests.support.fakes.github import FakeGitHub


def _task(
    *,
    source: EvidenceSource = "repo_files",
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


def test_apply_evidence_cap_rejects_large_file():
    with pytest.raises(EvidenceError, match="evidence.item_limit"):
        apply_evidence_cap(_task(max_file_size_bytes=100), [("big.txt", "x" * 500)])


@pytest.mark.asyncio
async def test_collect_repo_file_evidence_checks_selected_count_before_reading():
    repo_files = FakeGitHub(files={"present.txt": "here", "second.txt": "also"})
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
            return httpx2.Response(
                200,
                json={"tree": [{"type": "blob", "path": p} for p in ["a", "b", "c"]]},
            )
        requested_paths.append(request.url.path.rsplit("/", 1)[-1])
        if len(requested_paths) == 1:
            return httpx2.Response(200, text="successfully fetched first file")
        if failure == "network":
            raise httpx2.ReadTimeout("private connection details", request=request)
        return httpx2.Response(failure, text="private provider response")

    async with httpx2.AsyncClient(transport=httpx2.MockTransport(respond)) as client:
        monkeypatch.setattr(
            github_api, "get_github_client", AsyncMock(return_value=client)
        )
        # Tree discovery uses the API helper's own client reference.
        monkeypatch.setattr(
            "learn_to_cloud.verification.github_http._get_github_client",
            AsyncMock(return_value=client),
        )
        expected = (
            httpx2.ReadTimeout
            if failure == "network"
            else GitHubServerError
            if failure in (429, 503)
            else httpx2.HTTPStatusError
        )
        with pytest.raises(expected):
            await collect_repo_file_evidence(
                GitHubClient(), "owner", "repo", ["a", "b", "c"], _task()
            )

    assert requested_paths == ["a", "b"]


@pytest.mark.asyncio
async def test_disappearing_file_never_returns_partial_evidence():
    files = FakeGitHub(files={"a": "first", "c": "third"}, tree=["a", "b", "c"])
    task = _task()
    with pytest.raises(EvidenceError, match="evidence.changed"):
        await collect_repo_file_evidence(
            files,
            "owner",
            "repo",
            ["a", "b", "c"],
            task,
        )
