"""Tests for bounded verification error telemetry."""

from unittest.mock import MagicMock, patch

import httpx
import pytest

from learn_to_cloud_shared.verification.errors import github_error_to_result


def _status_error(
    status: int,
    *,
    headers: dict[str, str] | None = None,
) -> httpx.HTTPStatusError:
    request = httpx.Request("GET", "https://api.github.com/resource")
    response = httpx.Response(status, headers=headers, request=request)
    return httpx.HTTPStatusError("failed", request=request, response=response)


@pytest.mark.parametrize(
    ("error", "expected"),
    [
        (_status_error(401), "authentication"),
        (_status_error(403), "authorization"),
        (_status_error(403, headers={"X-RateLimit-Remaining": "0"}), "rate_limit"),
        (_status_error(403, headers={"Retry-After": "60"}), "rate_limit"),
        (_status_error(429), "rate_limit"),
        (_status_error(503), "provider_unavailable"),
        (_status_error(422), "client_error"),
    ],
)
def test_github_http_error_metric_uses_bounded_category(error, expected):
    counter = MagicMock()
    with patch(
        "learn_to_cloud_shared.verification.errors._GITHUB_API_ERROR_COUNTER",
        counter,
    ):
        github_error_to_result(error, event="github.request.failed")

    counter.add.assert_called_once_with(1, {"error.type": expected})


def test_github_network_error_metric_uses_bounded_category():
    counter = MagicMock()
    request = httpx.Request("GET", "https://api.github.com/resource")
    error = httpx.ConnectError("sensitive network detail", request=request)
    with patch(
        "learn_to_cloud_shared.verification.errors._GITHUB_API_ERROR_COUNTER",
        counter,
    ):
        github_error_to_result(error, event="github.request.failed")

    counter.add.assert_called_once_with(1, {"error.type": "network"})


@pytest.mark.parametrize(
    "message",
    [
        "You have exceeded a secondary rate limit.",
        "You have triggered an abuse detection mechanism.",
    ],
)
def test_github_403_body_can_identify_rate_limit(message):
    request = httpx.Request("GET", "https://api.github.com/resource")
    response = httpx.Response(
        403,
        json={"message": message},
        request=request,
    )
    error = httpx.HTTPStatusError("failed", request=request, response=response)
    counter = MagicMock()
    with patch(
        "learn_to_cloud_shared.verification.errors._GITHUB_API_ERROR_COUNTER",
        counter,
    ):
        github_error_to_result(error, event="github.request.failed")

    counter.add.assert_called_once_with(1, {"error.type": "rate_limit"})
