"""Tests for anonymous GHCR manifest verification."""

from collections.abc import Callable

import httpx
import pytest

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
