"""Production repository reads preserve their request and telemetry contracts."""

from unittest.mock import AsyncMock, MagicMock, Mock, patch

import httpx2
import pytest

from learn_to_cloud.verification import github_api, github_errors
from learn_to_cloud.verification.github_api import GitHub, GitHubClient
from learn_to_cloud.verification.github_errors import GitHubServerError


@pytest.mark.parametrize("status", [200, 404, 401, 403, 429, 500, 503])
async def test_raw_file_is_one_attempt_and_only_404_is_missing(status):
    requests = []
    span = MagicMock()

    def handler(request):
        requests.append(request)
        return httpx2.Response(
            status, text="private file content", headers={"Retry-After": "7"}
        )

    async with httpx2.AsyncClient(transport=httpx2.MockTransport(handler)) as client:
        with (
            patch.object(
                github_api, "get_github_client", AsyncMock(return_value=client)
            ),
            patch.object(
                github_api,
                "get_github_headers",
                return_value={"Accept": "application/vnd.github.v3+json"},
            ),
            patch.object(github_api.trace, "get_current_span", return_value=span),
            patch.object(github_errors.logger, "warning") as warning,
        ):
            adapter: GitHub = GitHubClient()
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
                with pytest.raises(httpx2.HTTPStatusError) as raised:
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


@pytest.mark.parametrize("error_type", [httpx2.ConnectError, httpx2.ReadTimeout])
async def test_raw_file_preserves_request_error_without_retry(error_type):
    error = error_type("private network details")
    handler = Mock(side_effect=error)

    async with httpx2.AsyncClient(transport=httpx2.MockTransport(handler)) as client:
        with (
            patch.object(
                github_api, "get_github_client", AsyncMock(return_value=client)
            ),
            patch.object(github_api, "get_github_headers", return_value={}),
            pytest.raises(error_type) as raised,
        ):
            await GitHubClient().file("owner", "repo", "README.md")
    assert raised.value is error
    handler.assert_called_once()


async def test_tree_forwards_branch_and_selects_only_blobs(monkeypatch):
    response = httpx2.Response(
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
    monkeypatch.setattr(github_api, "github_api_get", get)
    adapter: GitHub = GitHubClient()

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
        httpx2.ReadTimeout("upstream timeout"),
        GitHubServerError("upstream unavailable", status_code=503),
        httpx2.HTTPStatusError(
            "missing repository",
            request=httpx2.Request("GET", "https://api.github.com"),
            response=httpx2.Response(404),
        ),
    ],
)
async def test_tree_preserves_helper_errors(monkeypatch, error):
    get = AsyncMock(side_effect=error)
    monkeypatch.setattr(github_api, "github_api_get", get)

    with pytest.raises(type(error)) as raised:
        await GitHubClient().tree("owner", "repo")

    assert raised.value is error
    get.assert_awaited_once_with(
        "https://api.github.com/repos/owner/repo/git/trees/main",
        params={"recursive": 1},
    )
