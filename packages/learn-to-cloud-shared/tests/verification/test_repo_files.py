"""Raw reads distinguish a missing file from an unsuccessful evidence fetch."""

from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from learn_to_cloud_shared.verification import github_errors, repo_files
from learn_to_cloud_shared.verification.github_errors import GitHubServerError


@pytest.mark.parametrize("status", [200, 404, 401, 403, 429, 500, 503])
async def test_raw_file_is_one_attempt_and_only_404_is_missing(status):
    requests = []
    counter = MagicMock()

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
            patch.object(repo_files, "get_github_headers", return_value={}),
            patch.object(github_errors, "_GITHUB_API_ERROR_COUNTER", counter),
            patch.object(github_errors.logger, "warning") as warning,
        ):
            adapter = repo_files.GitHubRepoFiles()
            if status in {200, 404}:
                result = await adapter.file("owner", "repo", "README.md")
                assert result == ("private file content" if status == 200 else None)
            elif status == 429 or status >= 500:
                with pytest.raises(GitHubServerError) as raised:
                    await adapter.file("owner", "repo", "README.md")
                assert raised.value.status_code == status
                assert raised.value.retry_after == (7 if status == 429 else None)
                assert "private" not in str(raised.value)
            else:
                with pytest.raises(httpx.HTTPStatusError) as raised:
                    await adapter.file("owner", "repo", "README.md")
                assert raised.value.response.status_code == status
                assert raised.value.response.headers["Retry-After"] == "7"
    assert len(requests) == 1
    assert requests[0].url.host == "raw.githubusercontent.com"
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
