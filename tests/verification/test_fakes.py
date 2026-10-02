"""Reusable verification fakes retain the production calling interfaces."""

import pytest

from learn_to_cloud.verification.github_api import GitHub, WorkflowJob
from tests.support.fakes.github import FakeGitHub


async def test_fake_github_copies_inputs_and_returns_independent_trees():
    files = {"README.md": "original"}
    tree = ["README.md", "missing.md"]
    adapter: GitHub = FakeGitHub(files=files, tree=tree)
    files["README.md"] = "changed"
    tree.clear()

    result = await adapter.tree(owner="owner", repo="repo", branch="feature")
    assert result == ["README.md", "missing.md"]
    result.clear()
    assert await adapter.tree("owner", "repo") == ["README.md", "missing.md"]
    assert (
        await adapter.file(
            owner="owner", repo="repo", path="README.md", branch="feature"
        )
        == "original"
    )
    assert await adapter.file("owner", "repo", "missing.md") is None


async def test_fake_github_distinguishes_default_and_explicit_empty_tree():
    files = {"README.md": "content"}
    default = FakeGitHub(files=files)
    empty = FakeGitHub(files=files, tree=[])

    assert await default.tree("owner", "repo") == ["README.md"]
    assert await empty.tree("owner", "repo") == []
    assert await empty.file("owner", "repo", "README.md") == "content"
    assert await FakeGitHub().tree("owner", "repo") == []


async def test_fake_github_raises_the_configured_tree_error():
    error = RuntimeError("tree failure")
    adapter = FakeGitHub(tree_error=error)

    with pytest.raises(RuntimeError) as raised:
        await adapter.tree("owner", "repo")

    assert raised.value is error


@pytest.mark.parametrize("sha", [None, "current-head"])
async def test_fake_github_head_sha_accepts_compatible_keywords(sha):
    adapter: GitHub = FakeGitHub(sha=sha)

    assert await adapter.head_sha(owner="owner", repo="repo", branch="feature") == sha


@pytest.mark.parametrize("run", [None, {"head_sha": "current-head"}])
async def test_fake_github_latest_run_accepts_compatible_keywords(run):
    adapter: GitHub = FakeGitHub(run=run)

    assert (
        await adapter.latest_run(
            owner="owner", repo="repo", workflow="ci.yml", branch="feature"
        )
        is run
    )


async def test_fake_github_preserves_exception_identity():
    error = RuntimeError("upstream failure")
    github = FakeGitHub(sha_error=error, run_error=error)

    with pytest.raises(RuntimeError) as raised:
        await github.head_sha("owner", "repo")
    assert raised.value is error

    with pytest.raises(RuntimeError) as raised:
        await github.latest_run("owner", "repo", "ci.yml")
    assert raised.value is error


async def test_fake_github_returns_repository_metadata_and_jobs():
    job = WorkflowJob(
        id=1,
        run_id=2,
        run_attempt=3,
        head_sha="a" * 40,
        name="test",
        status="completed",
        conclusion="success",
    )
    github = FakeGitHub(repos={"owner/repo": {"name": "repo"}}, jobs=[job])

    assert await github.repo_metadata("owner", "repo") == {"name": "repo"}
    assert await github.repo_metadata("missing", "repo") is None
    assert await github.jobs_for_attempt("owner", "repo", 2, 3) == [job]
