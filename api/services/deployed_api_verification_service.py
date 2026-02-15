"""Deployed API verification for Phase 4 hands-on validation.

This module validates that users have successfully deployed their Journal API
by making a live HTTP request to their submitted endpoint.

Verification uses a challenge-response protocol to prove API ownership:
1. POST a unique challenge entry to /entries
2. GET /entries and confirm the challenge nonce appears
3. DELETE the challenge entry to clean up

The deployed API must:
- Be publicly accessible via HTTPS
- Have working POST /entries, GET /entries, and DELETE /entries/{id} endpoints
- Return valid JSON with journal entry structure

SCALABILITY:
- Circuit breaker fails fast when deployed API is unavailable (5 failures -> 60s)
- Retry with exponential backoff for transient failures (3 attempts)
- Connection pooling via shared httpx.AsyncClient
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
import secrets
from datetime import datetime
from typing import Any
from urllib.parse import urlparse

import httpx
from circuitbreaker import CircuitBreakerError, circuit
from tenacity import (
    RetryCallState,
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential_jitter,
)

from schemas import ValidationResult

logger = logging.getLogger(__name__)

# Shared HTTP client for deployed API requests (connection pooling)
_deployed_api_client: httpx.AsyncClient | None = None
_client_lock = asyncio.Lock()


class DeployedApiServerError(Exception):
    """Raised when deployed API returns a 5xx error (retriable)."""

    pass


# Exceptions that should trigger retry and circuit breaker
RETRIABLE_EXCEPTIONS: tuple[type[Exception], ...] = (
    httpx.RequestError,
    httpx.TimeoutException,
    DeployedApiServerError,
)

# UUID v4 pattern (standard format from Python's uuid module)
_UUID_PATTERN = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$",
    re.IGNORECASE,
)

# Required fields for a journal entry
_REQUIRED_FIELDS = {"id", "work", "struggle", "intention", "created_at"}

# String fields with max length constraint (256 chars per journal-starter schema)
_STRING_FIELDS_WITH_LIMIT = {"work", "struggle", "intention"}
_MAX_STRING_LENGTH = 256


async def _get_client() -> httpx.AsyncClient:
    """Get or create a shared HTTP client for deployed API requests.

    Uses connection pooling to reduce overhead from per-request client creation.
    Thread-safe via asyncio.Lock to prevent race conditions.
    """
    global _deployed_api_client

    if _deployed_api_client is not None and not _deployed_api_client.is_closed:
        return _deployed_api_client

    async with _client_lock:
        if _deployed_api_client is not None and not _deployed_api_client.is_closed:
            return _deployed_api_client

        _deployed_api_client = httpx.AsyncClient(
            timeout=httpx.Timeout(15.0, connect=5.0),
            follow_redirects=True,
            limits=httpx.Limits(max_connections=20, max_keepalive_connections=10),
        )
        return _deployed_api_client


async def close_deployed_api_client() -> None:
    """Close the shared HTTP client (called on application shutdown)."""
    global _deployed_api_client
    if _deployed_api_client is not None and not _deployed_api_client.is_closed:
        await _deployed_api_client.aclose()
    _deployed_api_client = None


def _is_valid_url(value: str) -> bool:
    """Check if a string is a valid HTTPS URL."""
    parsed = urlparse(value)
    return parsed.scheme == "https" and bool(parsed.netloc)


def _normalize_base_url(url: str) -> str:
    """Normalize the base URL by stripping trailing slashes and paths."""
    url = url.strip().rstrip("/")
    # Remove /entries or /entries/ suffix if user accidentally included it
    if url.endswith("/entries"):
        url = url[:-8]
    return url


def _validate_uuid(value: str) -> bool:
    """Check if a string is a valid UUID v4."""
    return bool(_UUID_PATTERN.match(value))


def _validate_datetime(value: str) -> bool:
    """Check if a string is a valid ISO 8601 datetime."""
    try:
        if value.endswith("Z"):
            value = value[:-1] + "+00:00"
        datetime.fromisoformat(value)
        return True
    except (ValueError, TypeError):
        return False


def _validate_entry(entry: dict, index: int) -> tuple[bool, str | None]:
    """Validate a single journal entry.

    Args:
        entry: The entry dict to validate
        index: The index of this entry in the array (for error messages)

    Returns:
        Tuple of (is_valid, error_message)
    """
    missing_fields = _REQUIRED_FIELDS - set(entry.keys())
    if missing_fields:
        return (
            False,
            f"Entry {index + 1} missing fields: {', '.join(sorted(missing_fields))}",
        )

    if not isinstance(entry.get("id"), str) or not _validate_uuid(entry["id"]):
        return False, f"Entry {index + 1} has invalid id (expected UUID format)"

    for field in _STRING_FIELDS_WITH_LIMIT:
        value = entry.get(field)
        if not isinstance(value, str):
            return False, f"Entry {index + 1} field '{field}' must be a string"
        if len(value) > _MAX_STRING_LENGTH:
            return False, f"Entry {index + 1} field '{field}' exceeds max length"
        if not value.strip():
            return False, f"Entry {index + 1} field '{field}' cannot be empty"

    # Validate created_at is a datetime
    created_at = entry.get("created_at")
    if not isinstance(created_at, str) or not _validate_datetime(created_at):
        return (
            False,
            f"Entry {index + 1} has invalid created_at (expected ISO 8601 datetime)",
        )

    # updated_at is optional but if present, must be valid datetime
    updated_at = entry.get("updated_at")
    if updated_at is not None:
        if not isinstance(updated_at, str) or not _validate_datetime(updated_at):
            return False, f"Entry {index + 1} has invalid updated_at"

    return True, None


def _validate_entries_json(data: list) -> ValidationResult:
    """Validate the entries array from the API response.

    Args:
        data: The parsed JSON array from the API response

    Returns:
        ValidationResult with validation status and feedback
    """
    if len(data) == 0:
        return ValidationResult(
            is_valid=False,
            message="No entries found. Create at least one journal entry first.",
        )

    for i, entry in enumerate(data):
        if not isinstance(entry, dict):
            return ValidationResult(
                is_valid=False,
                message=f"Entry {i + 1} is not a valid object.",
            )

        is_valid, error = _validate_entry(entry, i)
        if not is_valid:
            return ValidationResult(
                is_valid=False,
                message=error or "Entry validation failed",
            )

    count = len(data)
    entry_word = "entry" if count == 1 else "entries"
    return ValidationResult(
        is_valid=True,
        message=f"Deployed API verified! Found {count} valid {entry_word}.",
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


def _wait_exponential(retry_state: RetryCallState) -> float:
    """Exponential backoff with jitter."""
    return wait_exponential_jitter(initial=0.5, max=10)(retry_state)


@circuit(
    failure_threshold=5,
    recovery_timeout=60,
    expected_exception=RETRIABLE_EXCEPTIONS,
    name="deployed_api_circuit",
)
@retry(
    stop=stop_after_attempt(3),
    wait=_wait_exponential,
    retry=retry_if_exception_type(RETRIABLE_EXCEPTIONS),
    reraise=True,
)
async def _fetch_with_retry(
    url: str,
    *,
    method: str = "GET",
    json_body: dict | None = None,
) -> httpx.Response:
    """Make an HTTP request to the deployed API with retry logic.

    Args:
        url: The full URL to request
        method: HTTP method (GET, POST, DELETE)
        json_body: Optional JSON body for POST requests

    Returns:
        The httpx Response object

    Raises:
        DeployedApiServerError: If the API returns a 5xx error
        httpx.RequestError: For connection/network errors
        httpx.TimeoutException: If the request times out
    """
    client = await _get_client()
    response = await client.request(
        method,
        url,
        json=json_body,
        headers={"Accept": "application/json"},
    )

    if response.status_code >= 500:
        raise DeployedApiServerError(
            f"Server returned {response.status_code}: {response.text[:200]}"
        )

    return response


async def _cleanup_challenge_entry(
    entries_url: str,
    entry_id: str,
) -> None:
    """Best-effort DELETE of the challenge entry. Failures are logged, not raised."""
    try:
        delete_url = f"{entries_url}/{entry_id}"
        client = await _get_client()
        await client.delete(delete_url, timeout=httpx.Timeout(10.0, connect=5.0))
    except Exception:
        logger.debug(
            "deployed_api.challenge_cleanup_failed",
            extra={"entry_id": entry_id},
        )


def _handle_request_exception(
    exc: Exception,
    entries_url: str,
    *,
    step: str = "",
) -> ValidationResult:
    """Convert a request exception into a ValidationResult.

    Centralises error handling for circuit breaker, timeout, connection,
    and server errors that can occur during any HTTP call in the flow.
    """
    step_prefix = f"{step}: " if step else ""

    if isinstance(exc, CircuitBreakerError):
        logger.warning(
            "deployed_api.circuit_open",
            extra={"url": entries_url},
        )
        return ValidationResult(
            is_valid=False,
            message=(
                "Too many recent failures checking deployed APIs. "
                "Please try again in a minute."
            ),
            server_error=True,
        )

    if isinstance(exc, httpx.TimeoutException):
        logger.warning(
            "deployed_api.timeout",
            extra={"url": entries_url, "step": step},
        )
        return ValidationResult(
            is_valid=False,
            message=(
                f"{step_prefix}Request timed out. Ensure your API is accessible "
                "and responding quickly."
            ),
        )

    if isinstance(exc, DeployedApiServerError):
        logger.warning(
            "deployed_api.server_error",
            extra={"url": entries_url, "error": str(exc), "step": step},
        )
        return ValidationResult(
            is_valid=False,
            message=(
                f"{step_prefix}Your API returned a server error (5xx). "
                "Please check your deployment."
            ),
        )

    if isinstance(exc, httpx.RequestError):
        logger.warning(
            "deployed_api.request_error",
            extra={"url": entries_url, "error": str(exc), "step": step},
        )
        return ValidationResult(
            is_valid=False,
            message=(
                f"{step_prefix}Could not connect to your API. "
                f"Error: {type(exc).__name__}"
            ),
        )

    # Unexpected exception — re-raise so it's not silently swallowed
    raise exc  # pragma: no cover


async def validate_deployed_api(base_url: str) -> ValidationResult:
    """Validate a deployed Journal API via challenge-response.

    Proves the submitter owns and controls the API by:
    1. POSTing a challenge entry with a unique nonce
    2. GETting /entries and confirming the nonce appears
    3. DELETEing the challenge entry to clean up

    Args:
        base_url: The base URL of the deployed API (e.g., https://api.example.com)

    Returns:
        ValidationResult with validation status and feedback
    """
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

    entries_url = f"{base_url}/entries"
    nonce = _generate_challenge_nonce()
    challenge_entry_id: str | None = None

    # --- Step 1: POST challenge entry ---
    challenge_body = {
        "work": nonce,
        "struggle": "LTC verification challenge",
        "intention": "Proving API ownership",
    }

    try:
        post_response = await _fetch_with_retry(
            entries_url, method="POST", json_body=challenge_body
        )
    except (
        CircuitBreakerError,
        httpx.TimeoutException,
        httpx.RequestError,
        DeployedApiServerError,
    ) as exc:
        return _handle_request_exception(exc, entries_url, step="POST /entries")

    if post_response.status_code == 404:
        return ValidationResult(
            is_valid=False,
            message="POST /entries returned 404. Ensure the endpoint exists.",
        )

    if post_response.status_code == 422:
        return ValidationResult(
            is_valid=False,
            message=(
                "POST /entries returned 422 (validation error). "
                "Ensure POST /entries accepts {work, struggle, intention}."
            ),
        )

    if post_response.status_code not in (200, 201):
        return ValidationResult(
            is_valid=False,
            message=(
                f"POST /entries returned unexpected status "
                f"{post_response.status_code}. Expected 200 or 201."
            ),
        )

    try:
        post_data = post_response.json()
        if isinstance(post_data, dict):
            entry_obj = post_data.get("entry", post_data)
            if isinstance(entry_obj, dict):
                challenge_entry_id = entry_obj.get("id")
    except (json.JSONDecodeError, AttributeError):
        pass  # We'll still try GET — ID is only needed for cleanup

    # --- Step 2: GET /entries and find the nonce ---
    try:
        get_response = await _fetch_with_retry(entries_url)
    except (
        CircuitBreakerError,
        httpx.TimeoutException,
        httpx.RequestError,
        DeployedApiServerError,
    ) as exc:
        # Best-effort cleanup before returning error
        if challenge_entry_id:
            await _cleanup_challenge_entry(entries_url, challenge_entry_id)
        return _handle_request_exception(exc, entries_url, step="GET /entries")

    if get_response.status_code != 200:
        if challenge_entry_id:
            await _cleanup_challenge_entry(entries_url, challenge_entry_id)
        return ValidationResult(
            is_valid=False,
            message=(
                f"GET /entries returned status {get_response.status_code}. "
                "Expected 200."
            ),
        )

    try:
        get_data = get_response.json()
    except json.JSONDecodeError:
        if challenge_entry_id:
            await _cleanup_challenge_entry(entries_url, challenge_entry_id)
        return ValidationResult(
            is_valid=False,
            message="GET /entries did not return valid JSON.",
        )

    entries = _extract_entries_list(get_data)
    if entries is None:
        if challenge_entry_id:
            await _cleanup_challenge_entry(entries_url, challenge_entry_id)
        return ValidationResult(
            is_valid=False,
            message=(
                'GET /entries must return {"entries": [...], "count": N}. '
                "See the journal-starter for the expected format."
            ),
        )

    nonce_found = False
    for entry in entries:
        if isinstance(entry, dict) and entry.get("work") == nonce:
            nonce_found = True
            if not challenge_entry_id:
                challenge_entry_id = entry.get("id")
            break

    # --- Step 3: Cleanup ---
    if challenge_entry_id:
        await _cleanup_challenge_entry(entries_url, challenge_entry_id)

    if not nonce_found:
        logger.warning(
            "deployed_api.challenge_failed",
            extra={"url": base_url, "nonce": nonce},
        )
        return ValidationResult(
            is_valid=False,
            message=(
                "Ownership verification failed. "
                "We posted a challenge entry to your API but could not "
                "find it in GET /entries. Make sure your POST /entries "
                "persists data and GET /entries returns all entries."
            ),
        )

    # Also validate that the real entries have correct structure
    real_entries = [
        e
        for e in entries
        if isinstance(e, dict)
        and isinstance(e.get("work"), str)
        and not e["work"].startswith(_CHALLENGE_PREFIX)
    ]

    if real_entries:
        validation = _validate_entries_json(real_entries)
        if not validation.is_valid:
            return validation

    logger.info(
        "deployed_api.verified",
        extra={
            "url": base_url,
            "entries_count": len(real_entries),
            "challenge": "passed",
        },
    )

    count = len(real_entries)
    entry_word = "entry" if count == 1 else "entries"
    return ValidationResult(
        is_valid=True,
        message=(
            f"Deployed API verified! Ownership confirmed via challenge-response. "
            f"Found {count} valid {entry_word}."
        ),
    )
