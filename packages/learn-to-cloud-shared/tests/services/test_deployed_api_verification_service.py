"""Server-side target guards, one-shot transport, and safe error mapping."""

import asyncio
import socket
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from learn_to_cloud_shared.verification import deployed_api
from learn_to_cloud_shared.verification.deployed_api import (
    DeployedApiServerError,
    _check_response_ip,
    _is_private_ip,
    _SsrfError,
    _validate_url_target,
    validate_deployed_api,
)


@pytest.mark.parametrize(
    ("address", "blocked"),
    [
        ("127.0.0.1", True),
        ("::1", True),
        ("10.0.0.1", True),
        ("172.16.0.1", True),
        ("192.168.1.1", True),
        ("169.254.169.254", True),
        ("224.0.0.1", True),
        ("0.0.0.0", True),
        ("100.64.0.1", True),
        ("not-an-ip", True),
        ("8.8.8.8", False),
        ("1.1.1.1", False),
    ],
)
def test_private_ip_classification(address, blocked):
    assert _is_private_ip(address) is blocked


@pytest.mark.parametrize(
    "host", ["127.0.0.1", "[::1]", "10.0.0.1", "169.254.169.254", "100.64.0.1"]
)
async def test_private_target_is_rejected_before_any_request(host):
    with patch.object(deployed_api, "_get_client", AsyncMock()) as get_client:
        result = await validate_deployed_api(f"https://{host}")

    assert result.verification_completed
    assert not result.is_valid
    assert "publicly accessible" in result.message
    get_client.assert_not_awaited()


@pytest.mark.parametrize(
    ("addresses", "message"),
    [
        (["20.50.2.100"], None),
        (["127.0.0.1"], "publicly accessible"),
        (["20.50.2.100", "10.0.0.1"], "publicly accessible"),
        ([], "Could not resolve hostname"),
    ],
)
async def test_dns_target_validation(addresses, message):
    addrinfo = [(2, 1, 6, "", (address, 443)) for address in addresses]
    with patch.object(
        asyncio.get_running_loop(), "getaddrinfo", AsyncMock(return_value=addrinfo)
    ):
        result = await _validate_url_target("https://learner.example")

    if message is None:
        assert result is None
    else:
        assert message in result


async def test_unresolvable_dns_returns_learner_feedback():
    with patch.object(
        asyncio.get_running_loop(),
        "getaddrinfo",
        AsyncMock(side_effect=socket.gaierror("Name resolution failed")),
    ):
        result = await _validate_url_target("https://nonexistent.invalid")

    assert result == "Could not resolve hostname: nonexistent.invalid"


@pytest.mark.parametrize("peer", [None, ("20.50.2.100", 443)])
def test_public_or_unavailable_response_peer_is_allowed(peer):
    stream = MagicMock()
    stream.get_extra_info.return_value = peer
    _check_response_ip(httpx.Response(200, extensions={"network_stream": stream}))


def test_missing_response_stream_is_allowed():
    _check_response_ip(httpx.Response(200))


@pytest.mark.parametrize("address", ["10.0.0.1", "169.254.169.254"])
def test_private_response_peer_is_blocked(address):
    stream = MagicMock()
    stream.get_extra_info.return_value = (address, 443)
    response = httpx.Response(200, extensions={"network_stream": stream})
    with pytest.raises(_SsrfError):
        _check_response_ip(response)


@pytest.mark.parametrize("status", [500, 501, 503])
async def test_post_once_preserves_safe_server_error_data(status):
    requests = []

    def handler(request):
        requests.append(request)
        return httpx.Response(status, text="private learner response body")

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        with (
            patch.object(deployed_api, "_get_client", AsyncMock(return_value=client)),
            pytest.raises(DeployedApiServerError) as raised,
        ):
            await deployed_api._post_once("https://learner.example/entries")

    assert len(requests) == 1
    assert requests[0].method == "POST"
    assert raised.value.status_code == status
    assert raised.value.retry_after is None
    assert str(raised.value) == f"Server returned {status}"


@pytest.mark.parametrize("error_type", [httpx.ConnectError, httpx.ReadTimeout])
async def test_post_once_preserves_native_request_exceptions(error_type):
    requests = []
    error = error_type("private transport detail")

    def handler(request):
        requests.append(request)
        raise error

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        with (
            patch.object(deployed_api, "_get_client", AsyncMock(return_value=client)),
            pytest.raises(error_type) as raised,
        ):
            await deployed_api._post_once("https://learner.example/entries")

    assert raised.value is error
    assert len(requests) == 1
    assert requests[0].method == "POST"


@pytest.mark.parametrize(
    ("error", "category", "message"),
    [
        (
            httpx.ReadTimeout("private network detail"),
            "timeout",
            "Request timed out. Ensure your API is accessible and responding quickly.",
        ),
        (
            httpx.ConnectError("private network detail"),
            "request_error",
            "Could not connect to your API. Error: ConnectError",
        ),
    ],
)
def test_request_mapper_preserves_messages_and_completion(error, category, message):
    span = MagicMock()
    with patch.object(deployed_api.trace, "get_current_span", return_value=span):
        result = deployed_api.deployed_api_error_to_result(error)

    assert result.message == message
    assert result.verification_completed
    assert not result.is_valid
    span.set_attribute.assert_called_once_with("error.type", category)
    span.add_event.assert_called_once_with(
        f"deployed_api.{category}",
        {"error.type": category, "verification.operation": "request"},
    )


def test_mapper_rethrows_unsupported_exception():
    error = ValueError("programming error")
    with pytest.raises(ValueError) as raised:
        deployed_api.deployed_api_error_to_result(error)
    assert raised.value is error
