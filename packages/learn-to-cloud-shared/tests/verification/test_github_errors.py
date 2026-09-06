"""Tests for bounded verification error telemetry."""

from unittest.mock import MagicMock, patch

import httpx
import pytest

from learn_to_cloud_shared.verification import github_errors
from learn_to_cloud_shared.verification.deployed_api import DeployedApiServerError
from learn_to_cloud_shared.verification.errors import UpstreamResponseError
from learn_to_cloud_shared.verification.github_errors import (
    GitHubServerError,
    github_error_to_result,
)


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
        "learn_to_cloud_shared.verification.github_errors._GITHUB_API_ERROR_COUNTER",
        counter,
    ):
        github_error_to_result(error, event="github.request.failed")

    counter.add.assert_called_once_with(1, {"error.type": expected})


def test_github_network_error_metric_uses_bounded_category():
    counter = MagicMock()
    request = httpx.Request("GET", "https://api.github.com/resource")
    error = httpx.ConnectError("sensitive network detail", request=request)
    with patch(
        "learn_to_cloud_shared.verification.github_errors._GITHUB_API_ERROR_COUNTER",
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
        "learn_to_cloud_shared.verification.github_errors._GITHUB_API_ERROR_COUNTER",
        counter,
    ):
        github_error_to_result(error, event="github.request.failed")

    counter.add.assert_called_once_with(1, {"error.type": "rate_limit"})


@pytest.mark.parametrize(
    ("error", "category", "status"),
    [
        (_status_error(401), "authentication", 401),
        (_status_error(403), "authorization", 403),
        (_status_error(422), "client_error", 422),
        (_status_error(500), "provider_unavailable", 500),
        (GitHubServerError("private detail", status_code=429), "rate_limit", 429),
        (
            GitHubServerError("private detail", status_code=503),
            "provider_unavailable",
            503,
        ),
        (httpx.ConnectError("private detail"), "network", None),
        (httpx.ReadTimeout("private detail"), "network", None),
    ],
)
def test_all_telemetry_uses_same_safe_bounded_attributes(
    error, category, status, caplog
):
    span = MagicMock()
    counter = MagicMock()
    with (
        patch.object(github_errors, "_GITHUB_API_ERROR_COUNTER", counter),
        patch.object(github_errors.trace, "get_current_span", return_value=span),
    ):
        result = github_error_to_result(error, event="github.test_failure")

    attributes = {"error.type": category}
    if status is not None:
        attributes["http.response.status_code"] = status
    assert {
        call.args[0]: call.args[1] for call in span.set_attribute.call_args_list
    } == (attributes)
    span.add_event.assert_called_once_with("github.test_failure", attributes)
    counter.add.assert_called_once_with(1, {"error.type": category})
    assert len(caplog.records) == 1
    record = caplog.records[0]
    assert record.levelname == "WARNING"
    assert record.getMessage() == "github.test_failure"
    assert getattr(record, "error.type") == category
    assert getattr(record, "http.response.status_code", None) == status
    assert "private" not in str(record.__dict__)
    assert "private" not in result.message
    assert not result.is_valid
    assert not result.verification_completed
    if status is None:
        assert result.message == "Could not reach GitHub. Please try again later."
    else:
        assert result.message == f"GitHub API error ({status}). Try again later."


@pytest.mark.parametrize(
    "body", ["invalid JSON", "null", "[]", '"secret"', '{"message":42}']
)
def test_malformed_or_nonobject_403_body_remains_authorization(body):
    response = httpx.Response(
        403, text=body, request=httpx.Request("GET", "https://api.github.com/private")
    )
    error = httpx.HTTPStatusError(
        "private", request=response.request, response=response
    )
    with patch.object(github_errors, "_GITHUB_API_ERROR_COUNTER") as counter:
        result = github_error_to_result(error, event="github.test_failure")
    counter.add.assert_called_once_with(1, {"error.type": "authorization"})
    assert not result.verification_completed


def test_404_is_completed_missing_work_without_operational_telemetry(caplog):
    with (
        patch.object(github_errors, "_GITHUB_API_ERROR_COUNTER") as counter,
        patch.object(github_errors.trace, "get_current_span") as get_span,
    ):
        result = github_error_to_result(_status_error(404), event="github.test_failure")
    assert result.verification_completed
    assert not result.is_valid
    assert "not found" in result.message
    counter.add.assert_not_called()
    get_span.assert_not_called()
    assert not caplog.records


@pytest.mark.parametrize(
    "error",
    [
        ValueError("programming error"),
        UpstreamResponseError("another response", status_code=503),
        DeployedApiServerError("another provider", status_code=503),
    ],
)
def test_unsupported_errors_propagate_without_github_telemetry(error, caplog):
    with (
        patch.object(github_errors, "_GITHUB_API_ERROR_COUNTER") as counter,
        patch.object(github_errors.trace, "get_current_span") as get_span,
        pytest.raises(type(error)) as raised,
    ):
        github_error_to_result(error, event="github.test_failure")
    assert raised.value is error
    counter.add.assert_not_called()
    get_span.assert_not_called()
    assert not caplog.records
