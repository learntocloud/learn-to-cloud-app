"""Reusable verification fakes retain the production calling interfaces."""

import pytest

from learn_to_cloud_shared.verification.repo_files import RepoFiles
from learn_to_cloud_shared.verification.repo_ref import RepoRef
from learn_to_cloud_shared.verification.workflow_runs import WorkflowRuns
from tests.fakes.repo_files import InMemoryRepoFiles
from tests.fakes.repo_ref import InMemoryRepoRef
from tests.fakes.workflow_runs import InMemoryWorkflowRuns


async def test_repo_files_copies_inputs_and_returns_independent_trees():
    files = {"README.md": "original"}
    tree = ["README.md", "missing.md"]
    adapter: RepoFiles = InMemoryRepoFiles(files, tree=tree)
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


async def test_repo_files_distinguishes_default_and_explicit_empty_tree():
    files = {"README.md": "content"}
    default = InMemoryRepoFiles(files)
    empty = InMemoryRepoFiles(files, tree=[])

    assert await default.tree("owner", "repo") == ["README.md"]
    assert await empty.tree("owner", "repo") == []
    assert await empty.file("owner", "repo", "README.md") == "content"
    assert await InMemoryRepoFiles().tree("owner", "repo") == []


async def test_repo_files_raises_the_configured_error():
    error = RuntimeError("tree failure")
    adapter = InMemoryRepoFiles(tree_error=error)

    with pytest.raises(RuntimeError) as raised:
        await adapter.tree("owner", "repo")

    assert raised.value is error


@pytest.mark.parametrize("sha", [None, "current-head"])
async def test_repo_ref_accepts_compatible_keywords(sha):
    adapter: RepoRef = InMemoryRepoRef(sha)

    assert await adapter.head_sha(owner="owner", repo="repo", branch="feature") == sha


@pytest.mark.parametrize("run", [None, {"head_sha": "current-head"}])
async def test_workflow_runs_accepts_compatible_keywords(run):
    adapter: WorkflowRuns = InMemoryWorkflowRuns(run)

    assert (
        await adapter.latest_run(
            owner="owner", repo="repo", workflow="ci.yml", branch="feature"
        )
        is run
    )


async def test_reference_and_workflow_fakes_preserve_exception_identity():
    error = RuntimeError("upstream failure")
    reference = InMemoryRepoRef(error=error)
    runs = InMemoryWorkflowRuns(error=error)

    with pytest.raises(RuntimeError) as raised:
        await reference.head_sha("owner", "repo")
    assert raised.value is error

    with pytest.raises(RuntimeError) as raised:
        await runs.latest_run("owner", "repo", "ci.yml")
    assert raised.value is error
