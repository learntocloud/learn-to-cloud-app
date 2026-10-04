"""The Phase 5 live probe makes one GET /version and requires the current commit."""

import asyncio
from unittest.mock import AsyncMock, patch

import httpx2
import pytest

from learn_to_cloud.verification import deployed_api

SHA = "a" * 40


async def _probe(handler, url="https://journal.example", sha=SHA, peer="8.8.8.8"):
    requests: list[httpx2.Request] = []

    def handle(request):
        requests.append(request)
        response = handler(request)
        if isinstance(response, BaseException):
            raise response
        return response

    async with httpx2.AsyncClient(
        transport=httpx2.MockTransport(handle), follow_redirects=False
    ) as client:
        with (
            patch.object(
                asyncio.get_running_loop(),
                "getaddrinfo",
                AsyncMock(return_value=[(2, 1, 6, "", (peer, 443))]),
            ),
            patch.object(deployed_api, "_get_client", AsyncMock(return_value=client)),
        ):
            result = await deployed_api.verify_deployed_version(url, sha)
    return result, requests


@pytest.mark.parametrize(
    ("url", "path"),
    [
        ("https://journal.example", "/version"),
        (" https://journal.example/api/ ", "/api/version"),
    ],
)
async def test_matching_commit_passes_with_one_get(url, path):
    result, requests = await _probe(
        lambda _: httpx2.Response(200, json={"commit": SHA}), url=url
    )
    assert result.is_valid and result.verification_completed
    assert [(r.method, r.url.path) for r in requests] == [("GET", path)]
    assert requests[0].headers["Accept"] == "application/json"


@pytest.mark.parametrize(
    "response",
    [
        httpx2.Response(200, json={"commit": "b" * 40}),
        httpx2.Response(200, json={"commit": SHA[:7]}),
        httpx2.Response(200, json={"sha": SHA}),
        httpx2.Response(200, json=[SHA]),
        httpx2.Response(200, text="not json"),
        httpx2.Response(404),
        httpx2.Response(301, headers={"Location": "https://elsewhere.example"}),
    ],
)
async def test_wrong_or_missing_commit_is_a_completed_failure(response):
    result, requests = await _probe(lambda _: response)
    assert not result.is_valid and result.verification_completed
    assert len(requests) == 1


@pytest.mark.parametrize(
    "url", ["http://journal.example", "journal.example", "https://"]
)
async def test_non_https_url_is_rejected_before_any_request(url):
    result, requests = await _probe(lambda _: httpx2.Response(200), url=url)
    assert not result.is_valid
    assert "HTTPS" in result.message
    assert requests == []


async def test_private_target_is_rejected_before_any_request():
    result, requests = await _probe(
        lambda _: httpx2.Response(200, json={"commit": SHA}), peer="10.0.0.5"
    )
    assert not result.is_valid
    assert "publicly accessible" in result.message
    assert requests == []


@pytest.mark.parametrize(
    "failure",
    [
        httpx2.Response(503),
        httpx2.ConnectError("refused"),
        httpx2.ReadTimeout("slow"),
    ],
)
async def test_unreachable_app_is_a_completed_failure(failure):
    result, _ = await _probe(lambda _: failure)
    assert not result.is_valid and result.verification_completed
    assert result.message.startswith("GET /version: ")
