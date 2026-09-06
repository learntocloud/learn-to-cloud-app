"""Tests for anonymous GHCR manifest verification."""

from collections.abc import Callable
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from learn_to_cloud_shared.verification import ghcr
from learn_to_cloud_shared.verification.ghcr import verify_public_ghcr_image


async def _verify(handler: Callable[[httpx.Request], httpx.Response]):
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        return await verify_public_ghcr_image("TestUser", client)


def _token_response(request: httpx.Request) -> httpx.Response:
    return httpx.Response(200, json={"token": "public-token"}, request=request)


@pytest.mark.asyncio
async def test_public_latest_manifest_passes():
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if request.url.path == "/token":
            return _token_response(request)
        return httpx.Response(200, request=request)

    result = await _verify(handler)

    assert result.is_valid is True
    assert result.task_results is not None
    assert "ghcr.io/testuser/journal-api:latest" in result.task_results[0].feedback
    assert requests[0].url.params["scope"] == "repository:testuser/journal-api:pull"
    assert requests[1].url.path == "/v2/testuser/journal-api/manifests/latest"
    assert requests[1].headers["Authorization"] == "Bearer public-token"


@pytest.mark.asyncio
async def test_private_package_returns_actionable_failure():
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/token":
            return _token_response(request)
        return httpx.Response(403, request=request)

    result = await _verify(handler)

    assert result.is_valid is False
    assert result.verification_completed is True
    assert "not publicly pullable" in result.message
    assert result.task_results is not None
    assert "visibility to public" in result.task_results[0].next_steps


@pytest.mark.asyncio
async def test_missing_latest_manifest_returns_actionable_failure():
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/token":
            return _token_response(request)
        return httpx.Response(404, request=request)

    result = await _verify(handler)

    assert result.is_valid is False
    assert result.verification_completed is True
    assert "not found" in result.message
    assert result.task_results is not None
    assert "latest tag" in result.task_results[0].next_steps


@pytest.mark.asyncio
async def test_malformed_token_response_is_incomplete_verification():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={}, request=request)

    result = await _verify(handler)

    assert result.is_valid is False
    assert result.verification_completed is False
    assert "unexpected response" in result.message


@pytest.mark.asyncio
async def test_transient_manifest_failure_is_retried():
    manifest_attempts = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal manifest_attempts
        if request.url.path == "/token":
            return _token_response(request)
        manifest_attempts += 1
        status = 500 if manifest_attempts == 1 else 200
        return httpx.Response(status, request=request)

    result = await _verify(handler)

    assert result.is_valid is True
    assert manifest_attempts == 2


@pytest.mark.parametrize("phase", ["token", "manifest"])
@pytest.mark.parametrize("status", [429, 500, 503])
async def test_exhausted_response_errors_keep_status_and_operation_counts(
    phase, status
):
    paths = []
    span = MagicMock()

    def handler(request):
        paths.append(request.url.path)
        if phase == "manifest" and request.url.path == "/token":
            return _token_response(request)
        return httpx.Response(status, text="private response body")

    operation = ghcr._get_manifest_status.retry_with(sleep=AsyncMock())
    with (
        patch.object(ghcr, "_get_manifest_status", operation),
        patch.object(ghcr.trace, "get_current_span", return_value=span),
    ):
        result = await _verify(handler)

    assert paths.count("/token") == 3
    assert len(paths) == (3 if phase == "token" else 6)
    assert not result.is_valid
    assert not result.verification_completed
    assert result.message == "Could not reach GHCR to verify the container image."
    span.set_attribute.assert_any_call("http.response.status_code", status)
    span.add_event.assert_called_once_with(
        "ghcr.request_failed",
        {"error.type": "ghcr_unavailable", "http.response.status_code": status},
    )
    assert "private response body" not in str(span.mock_calls)
    assert "public-token" not in str(span.mock_calls)
    assert "private response body" not in result.model_dump_json()


@pytest.mark.parametrize("phase", ["token", "manifest"])
@pytest.mark.parametrize("error_type", [httpx.ConnectError, httpx.ReadTimeout])
async def test_network_failures_are_incomplete_without_response_status(
    phase, error_type
):
    paths = []
    span = MagicMock()

    def handler(request):
        paths.append(request.url.path)
        if phase == "manifest" and request.url.path == "/token":
            return _token_response(request)
        raise error_type("private network details")

    operation = ghcr._get_manifest_status.retry_with(sleep=AsyncMock())
    with (
        patch.object(ghcr, "_get_manifest_status", operation),
        patch.object(ghcr.trace, "get_current_span", return_value=span),
    ):
        result = await _verify(handler)
    assert paths.count("/token") == 3
    assert len(paths) == (3 if phase == "token" else 6)
    assert not result.verification_completed
    span.set_attribute.assert_called_once_with("error.type", "ghcr_unavailable")
    span.add_event.assert_called_once_with(
        "ghcr.request_failed", {"error.type": "ghcr_unavailable"}
    )


@pytest.mark.parametrize("body", ["not json", "[]", "null", "{}", '{"token":42}'])
async def test_unusable_token_response_is_protocol_error_without_retries(body):
    requests = []
    span = MagicMock()

    def handler(request):
        requests.append(request)
        return httpx.Response(200, text=body)

    with patch.object(ghcr.trace, "get_current_span", return_value=span):
        result = await _verify(handler)
    assert len(requests) == 1
    assert not result.verification_completed
    assert result.message == "GHCR returned an unexpected response."
    span.add_event.assert_called_once_with(
        "ghcr.request_failed", {"error.type": "ghcr_response_error"}
    )


async def test_unexpected_token_http_error_retains_status_without_retries():
    requests = []
    span = MagicMock()

    def handler(request):
        requests.append(request)
        return httpx.Response(422, text="private token details")

    with patch.object(ghcr.trace, "get_current_span", return_value=span):
        result = await _verify(handler)
    assert len(requests) == 1
    assert not result.verification_completed
    span.add_event.assert_called_once_with(
        "ghcr.request_failed",
        {"error.type": "ghcr_response_error", "http.response.status_code": 422},
    )
    span.set_attribute.assert_any_call("http.response.status_code", 422)


@pytest.mark.parametrize("phase", ["token", "manifest"])
@pytest.mark.parametrize("status", [401, 403, 404])
async def test_private_or_missing_image_stays_completed_without_retries(phase, status):
    paths = []

    def handler(request):
        paths.append(request.url.path)
        if phase == "manifest" and request.url.path == "/token":
            return _token_response(request)
        return httpx.Response(status)

    result = await _verify(handler)
    assert len(paths) == (1 if phase == "token" else 2)
    assert result.verification_completed
    assert not result.is_valid
    assert ("not found" if status == 404 else "not publicly pullable") in result.message


@pytest.mark.parametrize("phase", ["token", "manifest"])
async def test_transient_phase_recovery_retries_complete_operation(phase):
    paths = []
    failing_attempts = 0

    def handler(request):
        nonlocal failing_attempts
        paths.append(request.url.path)
        if phase == "manifest" and request.url.path == "/token":
            return _token_response(request)
        if phase == "token" and request.url.path != "/token":
            return httpx.Response(200)
        failing_attempts += 1
        if failing_attempts == 1:
            return httpx.Response(429)
        return _token_response(request) if phase == "token" else httpx.Response(200)

    operation = ghcr._get_manifest_status.retry_with(sleep=AsyncMock())
    with patch.object(ghcr, "_get_manifest_status", operation):
        result = await _verify(handler)
    assert result.is_valid
    assert paths.count("/token") == 2
    assert len(paths) == (3 if phase == "token" else 4)
