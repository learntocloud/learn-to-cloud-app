"""Tests for the evidence collector split (cap + per-source getters)."""

from unittest.mock import AsyncMock

import httpx
import pytest

from learn_to_cloud_shared.verification import repo_files as repo_files_module
from learn_to_cloud_shared.verification.evidence import (
    apply_evidence_cap,
    collect_repo_file_evidence,
    collect_repo_pattern_evidence,
    collect_submitted_text_evidence,
    select_repo_paths,
)
from learn_to_cloud_shared.verification.github_errors import GitHubServerError
from learn_to_cloud_shared.verification.repo_files import (
    GitHubRepoFiles,
    InMemoryRepoFiles,
)
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
    path_patterns: list[str] | None = None,
) -> VerificationTask:
    return VerificationTask(
        id="task-1",
        phase_id=3,
        name="Test task",
        evidence=EvidencePolicy(
            source=source,
            path_patterns=path_patterns or [],
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


def test_select_repo_paths_prioritizes_exact_paths_before_directories():
    selected = select_repo_paths(
        [
            "infra/z.tf",
            ".github/workflows/ci.yml",
            "Dockerfile",
            "infra/a.tf",
        ],
        ["Dockerfile", ".github/workflows/", "infra/"],
        max_files=3,
    )

    assert selected == [
        "Dockerfile",
        ".github/workflows/ci.yml",
        "infra/a.tf",
    ]


@pytest.mark.asyncio
async def test_collect_repo_pattern_evidence_preserves_paths_and_caps():
    repo_files = InMemoryRepoFiles(
        {
            "Dockerfile": "FROM python",
            "infra/a.tf": "resource a",
            "infra/b.tf": "resource b",
        }
    )
    bundle = await collect_repo_pattern_evidence(
        repo_files,
        "owner",
        "repo",
        _task(max_files=2, path_patterns=["Dockerfile", "infra/"]),
    )

    assert [item.path for item in bundle.items] == ["Dockerfile", "infra/a.tf"]
    assert [item.content for item in bundle.items] == ["FROM python", "resource a"]


@pytest.mark.asyncio
@pytest.mark.parametrize("discovered", [False, True])
@pytest.mark.parametrize("failure", [401, 403, 429, 503, "network"])
async def test_failed_later_file_never_returns_partial_evidence(
    monkeypatch, discovered, failure
):
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
            if discovered:
                await collect_repo_pattern_evidence(
                    GitHubRepoFiles(),
                    "owner",
                    "repo",
                    _task(path_patterns=["a", "b", "c"]),
                )
            else:
                await collect_repo_file_evidence(
                    GitHubRepoFiles(), "owner", "repo", ["a", "b", "c"], _task()
                )

    assert requested_paths == ["a", "b"]


@pytest.mark.asyncio
@pytest.mark.parametrize("discovered", [False, True])
async def test_missing_later_file_still_returns_available_evidence(discovered):
    files = InMemoryRepoFiles({"a": "first", "c": "third"}, tree=["a", "b", "c"])
    task = _task(path_patterns=["a", "b", "c"])
    if discovered:
        bundle = await collect_repo_pattern_evidence(files, "owner", "repo", task)
    else:
        bundle = await collect_repo_file_evidence(
            files, "owner", "repo", ["a", "b", "c"], task
        )
    assert [item.path for item in bundle.items] == ["a", "c"]
