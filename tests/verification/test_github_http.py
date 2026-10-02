"""Transport-level retry, status, and delay contracts for GitHub requests."""

from unittest.mock import AsyncMock, MagicMock, Mock, patch

import httpx2
import pytest

from learn_to_cloud.verification import github_errors, github_http
from learn_to_cloud.verification.github_errors import GitHubServerError
from tests.support.retrying import retry_with


@pytest.mark.parametrize("status", [429, 500, 503])
async def test_exhausted_http_errors_retain_status_and_map_once(status):
    calls = []
    sleeps = AsyncMock()
    span = MagicMock()

    def handler(request):
        calls.append(request)
        return httpx2.Response(
            status,
            headers={"Retry-After": "120"},
            text="private upstream body",
        )

    operation = retry_with(github_http.github_api_get, sleep=sleeps)
    async with httpx2.AsyncClient(transport=httpx2.MockTransport(handler)) as client:
        with (
            patch.object(
                github_http, "_get_github_client", AsyncMock(return_value=client)
            ),
            patch.object(github_http, "get_github_headers", return_value={}),
            patch.object(github_errors.trace, "get_current_span", return_value=span),
            patch.object(github_errors.logger, "warning") as warning,
        ):
            with pytest.raises(GitHubServerError) as raised:
                await operation("https://api.github.com/private-repo")
            warning.assert_not_called()
            result = github_errors.github_error_to_result(
                raised.value, event="test.github.failed"
            )

    assert len(calls) == 3
    assert [request.method for request in calls] == ["GET"] * 3
    assert sleeps.await_count == 2
    error = raised.value
    assert error.status_code == status
    assert error.retry_after == (120 if status == 429 else None)
    assert "private" not in str(error)
    assert not result.verification_completed
    assert result.message == f"GitHub API error ({status}). Try again later."
    category = "rate_limit" if status == 429 else "provider_unavailable"
    attributes = {"error.type": category, "http.response.status_code": status}
    span.add_event.assert_called_once_with("test.github.failed", attributes)
    warning.assert_called_once_with("test.github.failed", extra=attributes)
    if status == 429:
        assert [call.args[0] for call in sleeps.await_args_list] == [60, 60]


@pytest.mark.parametrize("status", [429, 503])
async def test_transient_http_recovery_returns_success(status):
    handler = Mock(
        side_effect=[
            httpx2.Response(status, json={"ok": True}),
            httpx2.Response(status, json={"ok": True}),
            httpx2.Response(200, json={"ok": True}),
        ]
    )

    async with httpx2.AsyncClient(transport=httpx2.MockTransport(handler)) as client:
        with (
            patch.object(
                github_http, "_get_github_client", AsyncMock(return_value=client)
            ),
            patch.object(github_http, "get_github_headers", return_value={}),
        ):
            result = await retry_with(github_http.github_api_get, sleep=AsyncMock())(
                "https://github.com/x"
            )
    assert [
        (call.args[0].method, str(call.args[0].url)) for call in handler.call_args_list
    ] == [("GET", "https://github.com/x")] * 3
    assert result.status_code == 200


@pytest.mark.parametrize("error_type", [httpx2.ConnectError, httpx2.ReadTimeout])
async def test_request_failures_retain_original_exception(error_type):
    error = error_type("private connectivity detail")
    handler = Mock(side_effect=error)

    async with httpx2.AsyncClient(transport=httpx2.MockTransport(handler)) as client:
        with (
            patch.object(
                github_http, "_get_github_client", AsyncMock(return_value=client)
            ),
            patch.object(github_http, "get_github_headers", return_value={}),
            pytest.raises(error_type) as raised,
        ):
            await retry_with(github_http.github_api_get, sleep=AsyncMock())(
                "https://github.com/x"
            )
    assert [
        (call.args[0].method, str(call.args[0].url)) for call in handler.call_args_list
    ] == [("GET", "https://github.com/x")] * 3
    assert raised.value is error


@pytest.mark.parametrize("status", [401, 403, 404, 422])
async def test_nonretriable_status_preserves_response(status):
    requests = []

    def handler(request):
        requests.append(request)
        return httpx2.Response(
            status, headers={"Retry-After": "55"}, text="private body"
        )

    sleep = AsyncMock()
    async with httpx2.AsyncClient(transport=httpx2.MockTransport(handler)) as client:
        with (
            patch.object(
                github_http, "_get_github_client", AsyncMock(return_value=client)
            ),
            patch.object(github_http, "get_github_headers", return_value={}),
        ):
            operation = retry_with(github_http.github_api_get, sleep=sleep)
            with pytest.raises(httpx2.HTTPStatusError) as raised:
                await operation("https://github.com/x")
            assert raised.value.response.status_code == status
            assert raised.value.response.headers["Retry-After"] == "55"
    assert len(requests) == 1
    sleep.assert_not_awaited()


@pytest.mark.parametrize(
    ("header", "expected"),
    [(None, None), ("invalid", None), ("5", 5)],
)
def test_retry_after_numeric_parsing(header, expected):
    assert github_http._parse_retry_after(header) == expected
