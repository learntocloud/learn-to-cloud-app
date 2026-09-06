"""Transport-level retry, status, and delay contracts for GitHub requests."""

from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from learn_to_cloud_shared.verification import github_errors, github_http
from learn_to_cloud_shared.verification.github_errors import GitHubServerError


@pytest.mark.parametrize("method", ["get", "head"])
@pytest.mark.parametrize("status", [429, 500, 503])
async def test_exhausted_http_errors_retain_status_and_map_once(method, status):
    calls = []
    sleeps = AsyncMock()
    span = MagicMock()
    counter = MagicMock()

    def handler(request):
        calls.append(request)
        return httpx.Response(
            status,
            headers={"Retry-After": "120"},
            text="private upstream body",
        )

    decorated = (
        github_http.github_api_get
        if method == "get"
        else github_http.github_head_status
    )
    operation = decorated.retry_with(sleep=sleeps)
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        with (
            patch.object(
                github_http, "_get_github_client", AsyncMock(return_value=client)
            ),
            patch.object(github_http, "get_github_headers", return_value={}),
            patch.object(github_errors, "_GITHUB_API_ERROR_COUNTER", counter),
            patch.object(github_errors.trace, "get_current_span", return_value=span),
            patch.object(github_errors.logger, "warning") as warning,
        ):
            with pytest.raises(GitHubServerError) as raised:
                await operation("https://api.github.com/private-repo")
            counter.add.assert_not_called()
            result = github_errors.github_error_to_result(
                raised.value, event="test.github.failed"
            )

    assert len(calls) == 3
    assert [request.method for request in calls] == [method.upper()] * 3
    assert sleeps.await_count == 2
    error = raised.value
    assert error.status_code == status
    assert error.retry_after == (120 if status == 429 else None)
    assert "private" not in str(error)
    assert not result.verification_completed
    assert result.message == f"GitHub API error ({status}). Try again later."
    category = "rate_limit" if status == 429 else "provider_unavailable"
    attributes = {"error.type": category, "http.response.status_code": status}
    counter.add.assert_called_once_with(1, {"error.type": category})
    span.add_event.assert_called_once_with("test.github.failed", attributes)
    warning.assert_called_once_with("test.github.failed", extra=attributes)
    if status == 429:
        assert [call.args[0] for call in sleeps.await_args_list] == [60, 60]


@pytest.mark.parametrize("method", ["get", "head"])
@pytest.mark.parametrize("status", [429, 503])
async def test_transient_http_recovery_returns_success(method, status):
    calls = 0

    def handler(request):
        nonlocal calls
        calls += 1
        return httpx.Response(status if calls < 3 else 200, json={"ok": True})

    decorated = (
        github_http.github_api_get
        if method == "get"
        else github_http.github_head_status
    )
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        with (
            patch.object(
                github_http, "_get_github_client", AsyncMock(return_value=client)
            ),
            patch.object(github_http, "get_github_headers", return_value={}),
        ):
            result = await decorated.retry_with(sleep=AsyncMock())(
                "https://github.com/x"
            )
    assert calls == 3
    assert (result.status_code if method == "get" else result) == 200


@pytest.mark.parametrize("method", ["get", "head"])
@pytest.mark.parametrize("error_type", [httpx.ConnectError, httpx.ReadTimeout])
async def test_request_failures_retain_original_exception(method, error_type):
    calls = 0
    error = error_type("private connectivity detail")

    def handler(request):
        nonlocal calls
        calls += 1
        raise error

    decorated = (
        github_http.github_api_get
        if method == "get"
        else github_http.github_head_status
    )
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        with (
            patch.object(
                github_http, "_get_github_client", AsyncMock(return_value=client)
            ),
            patch.object(github_http, "get_github_headers", return_value={}),
            pytest.raises(error_type) as raised,
        ):
            await decorated.retry_with(sleep=AsyncMock())("https://github.com/x")
    assert calls == 3
    assert raised.value is error


@pytest.mark.parametrize("method", ["get", "head"])
@pytest.mark.parametrize("status", [401, 403, 404, 422])
async def test_nonretriable_status_preserves_response(method, status):
    requests = []

    def handler(request):
        requests.append(request)
        return httpx.Response(
            status, headers={"Retry-After": "55"}, text="private body"
        )

    decorated = (
        github_http.github_api_get
        if method == "get"
        else github_http.github_head_status
    )
    sleep = AsyncMock()
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        with (
            patch.object(
                github_http, "_get_github_client", AsyncMock(return_value=client)
            ),
            patch.object(github_http, "get_github_headers", return_value={}),
        ):
            operation = decorated.retry_with(sleep=sleep)
            if method == "head" and status == 404:
                assert await operation("https://github.com/x") == 404
            else:
                with pytest.raises(httpx.HTTPStatusError) as raised:
                    await operation("https://github.com/x")
                assert raised.value.response.status_code == status
                assert raised.value.response.headers["Retry-After"] == "55"
    assert len(requests) == 1
    sleep.assert_not_awaited()


@pytest.mark.parametrize(
    ("header", "expected"),
    [(None, None), ("", None), ("invalid", None), ("5", 5), ("1.5", 1.5), ("0", 0)],
)
def test_retry_after_numeric_parsing(header, expected):
    assert github_http._parse_retry_after(header) == expected


@pytest.mark.parametrize("delay", [None, 0])
def test_missing_or_zero_retry_delay_preserves_jitter_fallback(delay):
    state = MagicMock()
    state.outcome.exception.return_value = GitHubServerError(
        "rate limited", status_code=429, retry_after=delay
    )
    with patch.object(github_http, "wait_exponential_jitter") as jitter:
        jitter.return_value.return_value = 0.75
        assert github_http._wait_with_retry_after(state) == 0.75
    jitter.assert_called_once_with(initial=0.5, max=10)
    jitter.return_value.assert_called_once_with(state)


@pytest.mark.parametrize(("delay", "expected"), [(1.5, 1.5), (120, 60)])
def test_retry_after_wait_is_capped(delay, expected):
    state = MagicMock()
    state.outcome.exception.return_value = GitHubServerError(
        "rate limited", status_code=429, retry_after=delay
    )
    with patch.object(github_http, "wait_exponential_jitter") as jitter:
        assert github_http._wait_with_retry_after(state) == expected
    jitter.assert_not_called()
