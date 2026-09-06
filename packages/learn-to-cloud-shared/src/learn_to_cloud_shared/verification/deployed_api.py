"""Create a journal entry and analyze it once, leaving the entry for the learner."""

from __future__ import annotations

import asyncio
import ipaddress
import json
import socket
from typing import Any
from urllib.parse import quote, urlparse

import httpx
from opentelemetry import trace

from learn_to_cloud_shared.core.config import get_worker_settings
from learn_to_cloud_shared.core.http_client import PooledClient
from learn_to_cloud_shared.schemas import ValidationResult
from learn_to_cloud_shared.verification.errors import UpstreamResponseError


class DeployedApiServerError(UpstreamResponseError):
    """Raised when the learner's API returns a 5xx response."""


def deployed_api_error_to_result(exc: Exception, *, step: str = "") -> ValidationResult:
    """Map deployed-API failures while retaining completed learner results."""
    step_prefix = f"{step}: " if step else ""
    span = trace.get_current_span()
    if isinstance(exc, httpx.TimeoutException):
        span.set_attribute("error.type", "timeout")
        span.add_event(
            "deployed_api.timeout",
            {"error.type": "timeout", "verification.operation": step or "request"},
        )
        return ValidationResult(
            is_valid=False,
            message=(
                f"{step_prefix}Request timed out. Ensure your API is accessible "
                "and responding quickly."
            ),
        )
    if isinstance(exc, DeployedApiServerError):
        span.set_attribute("error.type", "server_error")
        span.set_attribute("http.response.status_code", exc.status_code)
        span.add_event(
            "deployed_api.server_error",
            {
                "error.type": "server_error",
                "verification.operation": step or "request",
                "http.response.status_code": exc.status_code,
            },
        )
        return ValidationResult(
            is_valid=False,
            message=(
                f"{step_prefix}Your API returned a server error (5xx). "
                "Please check your deployment."
            ),
        )
    if isinstance(exc, httpx.RequestError):
        span.set_attribute("error.type", "request_error")
        span.add_event(
            "deployed_api.request_error",
            {
                "error.type": "request_error",
                "verification.operation": step or "request",
            },
        )
        return ValidationResult(
            is_valid=False,
            message=(
                f"{step_prefix}Could not connect to your API. "
                f"Error: {type(exc).__name__}"
            ),
        )
    raise exc


def _build_deployed_api_client() -> httpx.AsyncClient:
    return httpx.AsyncClient(
        timeout=httpx.Timeout(
            get_worker_settings().http.external_api_timeout,
            connect=5.0,
        ),
        follow_redirects=False,
        limits=httpx.Limits(max_connections=20, max_keepalive_connections=10),
    )


_pool = PooledClient(_build_deployed_api_client)


_VALID_SENTIMENTS = {"positive", "negative", "neutral"}
_ANALYSIS_TIMEOUT_SECONDS = 30.0


async def _get_client() -> httpx.AsyncClient:
    """Return the shared pooled HTTP client for deployed API requests."""
    return await _pool.get()


def _is_valid_url(value: str) -> bool:
    """Check if a string is a valid HTTPS URL."""
    try:
        parsed = urlparse(value)
        return (
            parsed.scheme == "https"
            and bool(parsed.hostname)
            and (parsed.port is None or parsed.port > 0)
        )
    except ValueError:
        return False


def _is_private_ip(addr: str) -> bool:
    """Check if an IP address is private or otherwise non-globally-routable."""
    try:
        ip = ipaddress.ip_address(addr)
    except ValueError:
        return True  # Unparseable — treat as unsafe
    # is_global covers private, loopback, link-local, reserved, unspecified,
    # CGNAT (100.64.0.0/10), and documentation ranges. Multicast addresses
    # incorrectly report is_global=True in Python 3.13, so we guard explicitly.
    return not ip.is_global or ip.is_multicast


async def _validate_url_target(url: str) -> str | None:
    """Reject private targets before sending requests from our server."""
    parsed = urlparse(url)
    hostname = parsed.hostname
    if not hostname:
        return "Invalid URL: no hostname."

    # Reject raw IP addresses that are private
    try:
        ip = ipaddress.ip_address(hostname)
        if _is_private_ip(str(ip)):
            span = trace.get_current_span()
            span.add_event(
                "deployed_api.ssrf_blocked",
                {"verification.reason": "private_ip_literal"},
            )
            return "URL must point to a publicly accessible server."
        return None
    except ValueError:
        pass  # hostname is a domain name, resolve it below

    # Resolve hostname and check all resulting IPs
    loop = asyncio.get_running_loop()
    try:
        addrinfo = await loop.getaddrinfo(
            hostname, parsed.port or 443, type=socket.SOCK_STREAM
        )
    except socket.gaierror:
        return f"Could not resolve hostname: {hostname}"

    if not addrinfo:
        return f"Could not resolve hostname: {hostname}"

    for _family, _type, _proto, _canonname, sockaddr in addrinfo:
        addr = sockaddr[0]
        if not isinstance(addr, str) or _is_private_ip(addr):
            span = trace.get_current_span()
            span.add_event(
                "deployed_api.ssrf_blocked",
                {"verification.reason": "private_ip_resolved"},
            )
            return "URL must point to a publicly accessible server."

    return None


class _SsrfError(Exception):
    """Raised when a response reveals a connection to a private IP."""


def _check_response_ip(response: httpx.Response) -> None:
    """Reject a private response peer; this cannot undo the request already sent."""
    stream = response.extensions.get("network_stream")
    if stream is None:
        return
    server_addr = stream.get_extra_info("server_addr")
    if server_addr is None:
        return
    addr = server_addr[0]
    if _is_private_ip(addr):
        span = trace.get_current_span()
        span.add_event(
            "deployed_api.ssrf_blocked",
            {"verification.reason": "dns_rebinding"},
        )
        raise _SsrfError(addr)


def _normalize_base_url(url: str) -> str:
    """Normalize the base URL by stripping trailing slashes and paths."""
    url = url.strip().rstrip("/")
    # Remove /entries or /entries/ suffix if user accidentally included it
    if url.endswith("/entries"):
        url = url[:-8]
    return url


def _validate_analysis_json(data: Any, entry_id: str) -> ValidationResult:
    """Validate the Journal API's live AI analysis response."""
    if not isinstance(data, dict):
        return ValidationResult(
            is_valid=False,
            message="AI analysis must return a JSON object.",
        )

    if data.get("entry_id") != entry_id:
        return ValidationResult(
            is_valid=False,
            message="AI analysis returned an unexpected entry_id.",
        )

    sentiment = data.get("sentiment")
    if not isinstance(sentiment, str) or sentiment not in _VALID_SENTIMENTS:
        return ValidationResult(
            is_valid=False,
            message=("AI analysis sentiment must be positive, negative, or neutral."),
        )

    summary = data.get("summary")
    if not isinstance(summary, str) or not summary.strip():
        return ValidationResult(
            is_valid=False,
            message="AI analysis summary must be a non-empty string.",
        )

    topics = data.get("topics")
    if (
        not isinstance(topics, list)
        or not topics
        or any(not isinstance(topic, str) or not topic.strip() for topic in topics)
    ):
        return ValidationResult(
            is_valid=False,
            message="AI analysis topics must be a non-empty list of strings.",
        )

    return ValidationResult(
        is_valid=True,
        message="Live AI analysis verified.",
    )


async def _post_once(
    url: str,
    *,
    json_body: dict | None = None,
    timeout: float | None = None,
) -> httpx.Response:
    """POST once with shared connection limits and response-peer checks."""
    client = await _get_client()
    request_options: dict[str, Any] = {
        "json": json_body,
        "headers": {"Accept": "application/json"},
    }
    if timeout is not None:
        request_options["timeout"] = timeout
    response = await client.post(url, **request_options)

    _check_response_ip(response)
    if response.status_code >= 500:
        raise DeployedApiServerError(
            f"Server returned {response.status_code}",
            status_code=response.status_code,
        )
    return response


async def _create_entry(entries_url: str) -> ValidationResult | str:
    """Create an encouraging entry and require its ID for analysis."""
    entry_body = {
        "work": "Nice work getting your Journal API online!",
        "struggle": "Every challenge is a chance to learn.",
        "intention": "Keep building, learning, and making progress.",
    }

    try:
        response = await _post_once(entries_url, json_body=entry_body)
    except _SsrfError:
        return ValidationResult(
            is_valid=False,
            message="URL must point to a publicly accessible server.",
        )
    except (
        httpx.TimeoutException,
        httpx.RequestError,
        DeployedApiServerError,
    ) as exc:
        return deployed_api_error_to_result(exc, step="POST /entries")

    if response.status_code == 404:
        return ValidationResult(
            is_valid=False,
            message="POST /entries returned 404. Ensure the endpoint exists.",
        )

    if response.status_code == 422:
        return ValidationResult(
            is_valid=False,
            message=(
                "POST /entries returned 422 (validation error). "
                "Ensure POST /entries accepts {work, struggle, intention}."
            ),
        )

    if response.status_code not in (200, 201):
        return ValidationResult(
            is_valid=False,
            message=(
                f"POST /entries returned unexpected status "
                f"{response.status_code}. Expected 200 or 201."
            ),
        )

    try:
        post_data = response.json()
    except (json.JSONDecodeError, UnicodeDecodeError):
        return ValidationResult(
            is_valid=False,
            message="POST /entries did not return valid JSON.",
        )

    if isinstance(post_data, dict):
        entry = post_data.get("entry", post_data)
        if isinstance(entry, dict):
            entry_id = entry.get("id")
            if isinstance(entry_id, str) and entry_id.strip():
                return entry_id

    return ValidationResult(
        is_valid=False,
        message=(
            "POST /entries must return the created entry with a non-empty string id."
        ),
    )


async def _verify_analysis(base_url: str, entry_id: str) -> ValidationResult:
    """Call the deployed AI endpoint and validate its response contract."""
    try:
        encoded_id = quote(entry_id, safe="")
    except UnicodeEncodeError:
        return ValidationResult(
            is_valid=False,
            message="POST /entries returned an invalid entry ID.",
        )
    analysis_url = f"{base_url}/entries/{encoded_id}/analyze"
    try:
        response = await _post_once(
            analysis_url,
            timeout=_ANALYSIS_TIMEOUT_SECONDS,
        )
    except _SsrfError:
        return ValidationResult(
            is_valid=False,
            message="URL must point to a publicly accessible server.",
        )
    except (
        httpx.TimeoutException,
        httpx.RequestError,
        DeployedApiServerError,
    ) as exc:
        result = deployed_api_error_to_result(
            exc,
            step="POST /entries/{id}/analyze",
        )
        if isinstance(exc, DeployedApiServerError) and exc.status_code == 501:
            return ValidationResult(
                is_valid=False,
                message=(
                    "POST /entries/{id}/analyze is not implemented. Complete the "
                    "Journal API AI analysis task and deploy it."
                ),
            )
        return result

    if response.status_code == 404:
        return ValidationResult(
            is_valid=False,
            message=(
                "POST /entries/{id}/analyze returned 404. Ensure the endpoint "
                "exists and the created entry can be analyzed."
            ),
        )
    if response.status_code != 200:
        return ValidationResult(
            is_valid=False,
            message=(
                "POST /entries/{id}/analyze returned unexpected status "
                f"{response.status_code}. Expected 200."
            ),
        )

    try:
        data = response.json()
    except (json.JSONDecodeError, UnicodeDecodeError):
        return ValidationResult(
            is_valid=False,
            message="POST /entries/{id}/analyze did not return valid JSON.",
        )
    return _validate_analysis_json(data, entry_id)


async def validate_deployed_api(base_url: str) -> ValidationResult:
    """Create and analyze one entry, reporting the first failed step."""
    base_url = _normalize_base_url(base_url)

    if not base_url:
        return ValidationResult(
            is_valid=False,
            message="Please submit your deployed API base URL.",
        )

    if not _is_valid_url(base_url):
        return ValidationResult(
            is_valid=False,
            message="Please submit a valid HTTP(S) URL.",
        )

    # SSRF protection: resolve hostname and block private/internal IPs
    ssrf_error = await _validate_url_target(base_url)
    if ssrf_error:
        return ValidationResult(
            is_valid=False,
            message=ssrf_error,
        )

    post_result = await _create_entry(f"{base_url}/entries")
    if isinstance(post_result, ValidationResult):
        return post_result

    analysis_result = await _verify_analysis(base_url, post_result)
    if not analysis_result.is_valid:
        return analysis_result

    span = trace.get_current_span()
    span.set_attribute("verification.deployed_api.verified", True)
    span.set_attribute("verification.deployed_api.ai_verified", True)
    return ValidationResult(
        is_valid=True,
        message="Deployed API verified! Entry creation and live AI analysis confirmed.",
    )
