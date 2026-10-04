"""Phase 6 live probes: plain HTTP must not serve the API and HTTPS must send HSTS."""

import asyncio
from unittest.mock import AsyncMock, patch

import httpx2
import pytest

from learn_to_cloud.verification import deployed_api

_HSTS = {"Strict-Transport-Security": "max-age=31536000; includeSubDomains"}


async def _probe(check, handler, url="https://journal.example", peer="8.8.8.8"):
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
            result = await check(url)
    return result, requests


@pytest.mark.parametrize(
    ("url", "probed"),
    [
        ("https://journal.example", "http://journal.example/version"),
        ("https://journal.example:8443/api/", "http://journal.example/api/version"),
    ],
)
async def test_plaintext_probe_uses_default_http_port_and_base_path(url, probed):
    _, requests = await _probe(
        deployed_api.verify_plaintext_http_blocked,
        lambda _: httpx2.Response(308, headers={"Location": "https://x.example"}),
        url=url,
    )
    assert [str(r.url) for r in requests] == [probed]


@pytest.mark.parametrize(
    "response",
    [
        httpx2.Response(301, headers={"Location": "https://journal.example/version"}),
        httpx2.Response(308, headers={"Location": "https://journal.example/version"}),
        httpx2.Response(403),
        httpx2.Response(503),
        httpx2.ConnectError("refused"),
        httpx2.ConnectTimeout("dropped"),
    ],
)
async def test_plaintext_redirected_refused_or_not_served_passes(response):
    result, requests = await _probe(
        deployed_api.verify_plaintext_http_blocked, lambda _: response
    )
    assert result.is_valid and result.verification_completed
    assert len(requests) == 1


@pytest.mark.parametrize(
    ("response", "text"),
    [
        (httpx2.Response(200, json={"commit": "a" * 40}), "returned 200"),
        (httpx2.Response(204), "returned 204"),
        (
            httpx2.Response(302, headers={"Location": "http://journal.example/"}),
            "not to an https:// URL",
        ),
        (httpx2.Response(302, headers={"Location": "/version"}), "not to an https"),
    ],
)
async def test_plaintext_success_or_non_https_redirect_fails(response, text):
    result, _ = await _probe(
        deployed_api.verify_plaintext_http_blocked, lambda _: response
    )
    assert not result.is_valid and result.verification_completed
    assert text in result.message


@pytest.mark.parametrize(
    "check", [deployed_api.verify_plaintext_http_blocked, deployed_api.verify_hsts]
)
@pytest.mark.parametrize(
    ("url", "peer", "text"),
    [
        ("http://journal.example", "8.8.8.8", "HTTPS"),
        ("https://journal.example", "10.0.0.5", "publicly accessible"),
    ],
)
async def test_unsafe_or_non_https_target_is_rejected_before_any_request(
    check, url, peer, text
):
    result, requests = await _probe(
        check, lambda _: httpx2.Response(200), url=url, peer=peer
    )
    assert not result.is_valid
    assert text in result.message
    assert requests == []


@pytest.mark.parametrize(
    "header",
    [
        "max-age=31536000",
        "max-age=300; includeSubDomains; preload",
        'includeSubDomains; MAX-AGE="60"',
    ],
)
async def test_hsts_with_positive_max_age_passes(header):
    result, requests = await _probe(
        deployed_api.verify_hsts,
        lambda _: httpx2.Response(200, headers={"Strict-Transport-Security": header}),
    )
    assert result.is_valid
    assert [(r.method, str(r.url)) for r in requests] == [
        ("GET", "https://journal.example/version")
    ]


@pytest.mark.parametrize(
    "headers",
    [
        {},
        {"Strict-Transport-Security": "max-age=0"},
        {"Strict-Transport-Security": "includeSubDomains"},
        {"Strict-Transport-Security": "max-age=abc"},
        {"Strict-Transport-Security": "my-max-age=600"},
    ],
)
async def test_missing_or_disabled_hsts_fails(headers):
    result, _ = await _probe(
        deployed_api.verify_hsts, lambda _: httpx2.Response(200, headers=headers)
    )
    assert not result.is_valid and result.verification_completed
    assert "Strict-Transport-Security" in result.message


@pytest.mark.parametrize(
    "failure",
    [httpx2.Response(502, headers=_HSTS), httpx2.ConnectError("bad certificate")],
)
async def test_unreachable_https_api_fails_the_hsts_check(failure):
    result, _ = await _probe(deployed_api.verify_hsts, lambda _: failure)
    assert not result.is_valid and result.verification_completed
    assert result.message.startswith("GET /version: ")
