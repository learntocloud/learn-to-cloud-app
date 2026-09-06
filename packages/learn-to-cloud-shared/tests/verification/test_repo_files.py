"""Production repository reads preserve their request and telemetry contracts."""

from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from learn_to_cloud_shared.verification import github_errors, repo_files
from learn_to_cloud_shared.verification.github_errors import GitHubServerError


@pytest.mark.parametrize("status", [200, 404, 401, 403, 429, 500, 503])
async def test_raw_file_is_one_attempt_and_only_404_is_missing(status):
    requests = []
    counter = MagicMock()
    span = MagicMock()

    def handler(request):
        requests.append(request)
        return httpx.Response(
            status, text="private file content", headers={"Retry-After": "7"}
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        with (
            patch.object(
                repo_files, "get_github_client", AsyncMock(return_value=client)
            ),
            patch.object(
                repo_files,
                "get_github_headers",
                return_value={"Accept": "application/vnd.github.v3+json"},
            ),
            patch.object(repo_files.trace, "get_current_span", return_value=span),
            patch.object(github_errors, "_GITHUB_API_ERROR_COUNTER", counter),
            patch.object(github_errors.logger, "warning") as warning,
        ):
            adapter: repo_files.RepoFiles = repo_files.GitHubRepoFiles()
            if status in {200, 404}:
                result = await adapter.file(
                    owner="owner", repo="repo", path="README.md", branch="feature"
                )
                assert result == ("private file content" if status == 200 else None)
            elif status == 429 or status >= 500:
                with pytest.raises(GitHubServerError) as raised:
                    await adapter.file("owner", "repo", "README.md", "feature")
                assert raised.value.status_code == status
                assert raised.value.retry_after == (7 if status == 429 else None)
                assert "private" not in str(raised.value)
            else:
                with pytest.raises(httpx.HTTPStatusError) as raised:
                    await adapter.file("owner", "repo", "README.md", "feature")
                assert raised.value.response.status_code == status
                assert raised.value.response.headers["Retry-After"] == "7"
    assert len(requests) == 1
    assert requests[0].url.host == "raw.githubusercontent.com"
    assert requests[0].url.path == "/owner/repo/feature/README.md"
    assert requests[0].headers["Accept"] == "application/vnd.github.v3+json"
    if status == 404:
        span.add_event.assert_called_once_with("github.repo_file.fetch_failed")
    else:
        span.add_event.assert_not_called()
    warning.assert_not_called()
    counter.add.assert_not_called()


@pytest.mark.parametrize("error_type", [httpx.ConnectError, httpx.ReadTimeout])
async def test_raw_file_preserves_request_error_without_retry(error_type):
    calls = 0
    error = error_type("private network details")

    def handler(request):
        nonlocal calls
        calls += 1
        raise error

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        with (
            patch.object(
                repo_files, "get_github_client", AsyncMock(return_value=client)
            ),
            patch.object(repo_files, "get_github_headers", return_value={}),
            pytest.raises(error_type) as raised,
        ):
            await repo_files.GitHubRepoFiles().file("owner", "repo", "README.md")
    assert raised.value is error
    assert calls == 1


async def test_tree_forwards_branch_and_selects_only_blobs(monkeypatch):
    response = httpx.Response(
        200,
        json={
            "tree": [
                {"type": "tree", "path": "src"},
                {"type": "blob", "path": "src/main.py"},
                {"type": "commit", "path": "submodule"},
                {"type": "blob", "path": "README.md"},
            ]
        },
    )
    get = AsyncMock(return_value=response)
    monkeypatch.setattr(repo_files, "github_api_get", get)
    adapter: repo_files.RepoFiles = repo_files.GitHubRepoFiles()

    assert await adapter.tree(owner="owner", repo="repo", branch="feature") == [
        "src/main.py",
        "README.md",
    ]
    get.assert_awaited_once_with(
        "https://api.github.com/repos/owner/repo/git/trees/feature",
        params={"recursive": 1},
    )


@pytest.mark.parametrize(
    "error",
    [
        httpx.ReadTimeout("upstream timeout"),
        GitHubServerError("upstream unavailable", status_code=503),
        httpx.HTTPStatusError(
            "missing repository",
            request=httpx.Request("GET", "https://api.github.com"),
            response=httpx.Response(404),
        ),
    ],
)
async def test_tree_preserves_helper_errors(monkeypatch, error):
    get = AsyncMock(side_effect=error)
    monkeypatch.setattr(repo_files, "github_api_get", get)

    with pytest.raises(type(error)) as raised:
        await repo_files.GitHubRepoFiles().tree("owner", "repo")

    assert raised.value is error
    get.assert_awaited_once_with(
        "https://api.github.com/repos/owner/repo/git/trees/main",
        params={"recursive": 1},
    )


def test_default_adapter_is_shared_and_does_not_request_a_client(monkeypatch):
    get_client = AsyncMock()
    monkeypatch.setattr(repo_files, "get_github_client", get_client)

    first = repo_files.default_repo_files()

    assert isinstance(first, repo_files.GitHubRepoFiles)
    assert repo_files.default_repo_files() is first
    get_client.assert_not_called()
