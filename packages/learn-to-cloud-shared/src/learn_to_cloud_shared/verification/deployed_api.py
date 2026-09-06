"""Deployed API verification for Phase 4 hands-on validation.

This module validates that users have successfully deployed their Journal API
by making a live HTTP request to their submitted endpoint.

Verification uses a challenge-response protocol to prove API ownership:
1. POST a unique challenge entry to /entries
2. GET /entries and validate only the entry matching the current challenge nonce
3. POST /entries/{id}/analyze and validate the live AI response

The entry remains as an encouraging milestone, even if verification fails.

The deployed API must:
- Be publicly accessible via HTTPS
- Have working create, list, and analyze endpoints
- Return valid journal entry and AI analysis JSON

SCALABILITY:
- Retry create/list verification requests with exponential backoff (3 attempts)
- Send exactly one potentially billable AI analysis request
- Connection pooling via shared httpx.AsyncClient
"""

from __future__ import annotations

import asyncio
import ipaddress
import json
import secrets
import socket
from datetime import datetime
from typing import Any
from urllib.parse import urlparse
from uuid import UUID

import httpx
from opentelemetry import trace
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential_jitter,
)

from learn_to_cloud_shared.core.config import get_worker_settings
from learn_to_cloud_shared.core.http_client import PooledClient
from learn_to_cloud_shared.schemas import ValidationResult
from learn_to_cloud_shared.verification.errors import (
    UpstreamResponseError,
    make_retriable,
)


class DeployedApiServerError(UpstreamResponseError):
    """Raised when the learner's API returns a retriable 5xx response."""


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


# Exceptions that should trigger retry
RETRIABLE_EXCEPTIONS: tuple[type[Exception], ...] = make_retriable(
    DeployedApiServerError
)

# Required fields for a journal entry
_REQUIRED_FIELDS = {"id", "work", "struggle", "intention", "created_at"}

# String fields with max length constraint (256 chars per journal-starter schema)
_STRING_FIELDS_WITH_LIMIT = {"work", "struggle", "intention"}
_MAX_STRING_LENGTH = 256
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
    """Validate that a URL's hostname does not target a private IP address.

    Performs pre-flight DNS resolution to catch obvious SSRF attempts
    (direct IPs, hostnames resolving to private ranges). A second
    validation occurs post-connect in ``_check_response_ip`` to close
    the DNS-rebinding TOCTOU window.

    Returns None if safe, or an error message string.
    """
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
    """Verify the actual connected IP is not private (closes DNS-rebinding gap).

    Raises:
        _SsrfError: If the connection was made to a private/internal IP.
    """
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


def _validate_uuid(value: str) -> bool:
    """Check if a string is a valid UUID v4."""
    try:
        return UUID(value).version == 4
    except (ValueError, AttributeError, TypeError):
        return False


def _validate_datetime(value: str) -> bool:
    """Check if a string is a valid ISO 8601 datetime."""
    try:
        if value.endswith("Z"):
            value = value[:-1] + "+00:00"
        datetime.fromisoformat(value)
        return True
    except (ValueError, TypeError):
        return False


def _validate_entry(entry: dict) -> tuple[bool, str | None]:
    """Validate the current challenge entry's fields."""
    missing_fields = _REQUIRED_FIELDS - set(entry.keys())
    if missing_fields:
        return (
            False,
            f"Challenge entry missing fields: {', '.join(sorted(missing_fields))}",
        )

    if not isinstance(entry.get("id"), str) or not _validate_uuid(entry["id"]):
        return False, "Challenge entry has invalid id (expected UUID format)"

    for field in _STRING_FIELDS_WITH_LIMIT:
        value = entry.get(field)
        if not isinstance(value, str):
            return False, f"Challenge entry field '{field}' must be a string"
        if len(value) > _MAX_STRING_LENGTH:
            return False, f"Challenge entry field '{field}' exceeds max length"
        if not value.strip():
            return False, f"Challenge entry field '{field}' cannot be empty"

    # Validate created_at is a datetime
    created_at = entry.get("created_at")
    if not isinstance(created_at, str) or not _validate_datetime(created_at):
        return (
            False,
            "Challenge entry has invalid created_at (expected ISO 8601 datetime)",
        )

    # updated_at is optional but if present, must be valid datetime
    updated_at = entry.get("updated_at")
    if updated_at is not None and (
        not isinstance(updated_at, str) or not _validate_datetime(updated_at)
    ):
        return False, "Challenge entry has invalid updated_at"

    return True, None


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


_CHALLENGE_PREFIX = "ltc-verify-"


def _generate_challenge_nonce() -> str:
    """Generate a unique challenge nonce for ownership verification."""
    return f"{_CHALLENGE_PREFIX}{secrets.token_hex(16)}"


def _extract_entries_list(data: Any) -> list | None:
    """Extract the entries list from a GET /entries response.

    The journal-starter returns: {"entries": [...], "count": N}
    This is the only format we accept.

    Returns None if the format is unrecognised.
    """
    if isinstance(data, dict):
        entries = data.get("entries")
        if isinstance(entries, list):
            return entries
    return None


async def _fetch_once(
    url: str,
    *,
    method: str = "GET",
    json_body: dict | None = None,
    timeout: float | None = None,
) -> httpx.Response:
    """Make one HTTP request to the deployed API."""
    client = await _get_client()
    request_options: dict[str, Any] = {
        "json": json_body,
        "headers": {"Accept": "application/json"},
    }
    if timeout is not None:
        request_options["timeout"] = timeout
    response = await client.request(method, url, **request_options)

    _check_response_ip(response)
    if response.status_code >= 500:
        raise DeployedApiServerError(
            f"Server returned {response.status_code}",
            status_code=response.status_code,
        )
    return response


@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential_jitter(initial=0.5, max=10),
    retry=retry_if_exception_type(RETRIABLE_EXCEPTIONS),
    reraise=True,
)
async def _fetch_with_retry(
    url: str,
    *,
    method: str = "GET",
    json_body: dict | None = None,
    timeout: float | None = None,
) -> httpx.Response:
    """Make a retryable HTTP request to the deployed API.

    Args:
        url: The full URL to request
        method: HTTP method (GET or POST)
        json_body: Optional JSON body for POST requests
        timeout: Optional per-request timeout override

    Returns:
        The httpx Response object

    Raises:
        _SsrfError: If the connection resolved to a private IP
        DeployedApiServerError: If the API returns a 5xx error
        httpx.RequestError: For connection/network errors
        httpx.TimeoutException: If the request times out
    """
    return await _fetch_once(
        url,
        method=method,
        json_body=json_body,
        timeout=timeout,
    )


async def _post_challenge(
    entries_url: str, challenge_work: str
) -> ValidationResult | str | None:
    """POST a challenge entry to prove API ownership.

    Returns:
        ValidationResult if the POST failed (error for user).
        str if the entry_id was extracted from the response.
        None if POST succeeded but entry_id couldn't be parsed.
    """
    challenge_body = {
        "work": challenge_work,
        "struggle": "Every challenge is a chance to learn.",
        "intention": "Keep building, learning, and making progress.",
    }

    try:
        response = await _fetch_with_retry(
            entries_url, method="POST", json_body=challenge_body
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

    # The GET response can supply the ID if POST omits it.
    try:
        post_data = response.json()
        if isinstance(post_data, dict):
            entry_obj = post_data.get("entry", post_data)
            if isinstance(entry_obj, dict):
                entry_id = entry_obj.get("id")
                if isinstance(entry_id, str):
                    return entry_id
    except (json.JSONDecodeError, UnicodeDecodeError):
        pass

    return None


async def _verify_challenge(
    entries_url: str, challenge_work: str
) -> tuple[ValidationResult, str | None]:
    """Validate the exact challenge entry and return its ID for analysis."""
    try:
        response = await _fetch_with_retry(entries_url)
    except _SsrfError:
        return (
            ValidationResult(
                is_valid=False,
                message="URL must point to a publicly accessible server.",
            ),
            None,
        )
    except (
        httpx.TimeoutException,
        httpx.RequestError,
        DeployedApiServerError,
    ) as exc:
        return deployed_api_error_to_result(exc, step="GET /entries"), None

    if response.status_code != 200:
        return (
            ValidationResult(
                is_valid=False,
                message=(
                    f"GET /entries returned status {response.status_code}. "
                    "Expected 200."
                ),
            ),
            None,
        )

    try:
        get_data = response.json()
    except (json.JSONDecodeError, UnicodeDecodeError):
        return (
            ValidationResult(
                is_valid=False,
                message="GET /entries did not return valid JSON.",
            ),
            None,
        )

    entries = _extract_entries_list(get_data)
    if entries is None:
        return (
            ValidationResult(
                is_valid=False,
                message=(
                    'GET /entries must return {"entries": [...], "count": N}. '
                    "See the journal-starter for the expected format."
                ),
            ),
            None,
        )

    challenge_entry = next(
        (
            entry
            for entry in entries
            if isinstance(entry, dict) and entry.get("work") == challenge_work
        ),
        None,
    )
    if challenge_entry is None:
        span = trace.get_current_span()
        span.add_event("deployed_api.challenge_failed")
        return (
            ValidationResult(
                is_valid=False,
                message=(
                    "Ownership verification failed. "
                    "We posted a challenge entry to your API but could not "
                    "find it in GET /entries. Make sure your POST /entries "
                    "persists data and GET /entries returns all entries."
                ),
            ),
            None,
        )

    entry_id = challenge_entry.get("id")
    discovered_id = entry_id if isinstance(entry_id, str) else None
    is_valid, error = _validate_entry(challenge_entry)
    if not is_valid:
        return (
            ValidationResult(
                is_valid=False,
                message=error or "Challenge entry validation failed.",
            ),
            discovered_id,
        )

    span = trace.get_current_span()
    span.set_attribute("verification.deployed_api.challenge_verified", True)

    return (
        ValidationResult(
            is_valid=True,
            message=(
                "Deployed API verified! Ownership confirmed via challenge-response."
            ),
        ),
        discovered_id,
    )


async def _verify_analysis(base_url: str, entry_id: str) -> ValidationResult:
    """Call the deployed AI endpoint and validate its response contract."""
    analysis_url = f"{base_url}/entries/{entry_id}/analyze"
    try:
        response = await _fetch_once(
            analysis_url,
            method="POST",
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
                "exists and the challenge entry can be analyzed."
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
    """Verify ownership, challenge fields, and live AI analysis, leaving the entry."""
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

    entries_url = f"{base_url}/entries"
    challenge_work = (
        f"Nice work getting your Journal API online! ({_generate_challenge_nonce()})"
    )
    post_result = await _post_challenge(entries_url, challenge_work)
    if isinstance(post_result, ValidationResult):
        return post_result
    challenge_entry_id = post_result

    verify_result, discovered_id = await _verify_challenge(entries_url, challenge_work)
    if challenge_entry_id is None:
        challenge_entry_id = discovered_id
    if not verify_result.is_valid:
        return verify_result
    if not challenge_entry_id:
        return ValidationResult(
            is_valid=False,
            message=(
                "Ownership was confirmed, but the API did not return the "
                "challenge entry ID required for AI analysis."
            ),
        )

    analysis_result = await _verify_analysis(base_url, challenge_entry_id)
    if not analysis_result.is_valid:
        return analysis_result

    span = trace.get_current_span()
    span.set_attribute("verification.deployed_api.verified", True)
    span.set_attribute("verification.deployed_api.ai_verified", True)
    return ValidationResult(
        is_valid=True,
        message=f"{verify_result.message} Live AI analysis verified.",
    )
