"""Deployed API verification for Phase 4 hands-on validation.

This module validates that users have successfully deployed their Journal API
by making a live HTTP request to their submitted endpoint.

The deployed API must:
- Be publicly accessible via HTTPS
- Have a /entries endpoint that returns 2xx status
- Return valid JSON array with at least one journal entry
- Have entries with required fields: id, work, struggle, intention, created_at

SCALABILITY:
- Circuit breaker fails fast when deployed API is unavailable (5 failures -> 60s)
- Retry with exponential backoff for transient failures (3 attempts)
- Connection pooling via shared httpx.AsyncClient
"""

import asyncio
import json
import logging
import re
from datetime import datetime
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
        # Double-check after acquiring lock
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
    # Check required fields
    missing_fields = _REQUIRED_FIELDS - set(entry.keys())
    if missing_fields:
        return (
            False,
            f"Entry {index + 1} missing fields: {', '.join(sorted(missing_fields))}",
        )

    # Validate id is a UUID
    if not isinstance(entry.get("id"), str) or not _validate_uuid(entry["id"]):
        return False, f"Entry {index + 1} has invalid id (expected UUID format)"

    # Validate string fields
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
    # Must have at least one entry
    if len(data) == 0:
        return ValidationResult(
            is_valid=False,
            message="No entries found. Create at least one journal entry first.",
        )

    # Validate each entry
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
async def _fetch_entries_with_retry(entries_url: str) -> httpx.Response:
    """Fetch entries from the deployed API with retry logic.

    Args:
        entries_url: The full URL to the /entries endpoint

    Returns:
        The httpx Response object

    Raises:
        DeployedApiServerError: If the API returns a 5xx error
        httpx.RequestError: For connection/network errors
        httpx.TimeoutException: If the request times out
    """
    client = await _get_client()
    response = await client.get(
        entries_url,
        headers={"Accept": "application/json"},
    )

    # Treat 5xx as retriable server errors
    if response.status_code >= 500:
        raise DeployedApiServerError(
            f"Server returned {response.status_code}: {response.text[:200]}"
        )

    return response


async def validate_deployed_api(base_url: str) -> ValidationResult:
    """Validate a deployed Journal API by calling GET /entries.

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

    try:
        response = await _fetch_entries_with_retry(entries_url)
    except CircuitBreakerError:
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
        )
    except httpx.TimeoutException:
        logger.warning(
            "deployed_api.timeout",
            extra={"url": entries_url},
        )
        return ValidationResult(
            is_valid=False,
            message=(
                "Request timed out. Ensure your API is accessible "
                "and responding quickly."
            ),
        )
    except httpx.RequestError as e:
        logger.warning(
            "deployed_api.request_error",
            extra={"url": entries_url, "error": str(e)},
        )
        return ValidationResult(
            is_valid=False,
            message=f"Could not connect to your API. Error: {type(e).__name__}",
        )
    except DeployedApiServerError as e:
        logger.warning(
            "deployed_api.server_error",
            extra={"url": entries_url, "error": str(e)},
        )
        return ValidationResult(
            is_valid=False,
            message=(
                "Your API returned a server error (5xx). "
                "Please check your deployment."
            ),
        )

    # Check for non-success status codes
    if response.status_code == 404:
        return ValidationResult(
            is_valid=False,
            message="GET /entries returned 404. Ensure the endpoint exists.",
        )

    if response.status_code == 401 or response.status_code == 403:
        return ValidationResult(
            is_valid=False,
            message=(
                f"GET /entries returned {response.status_code}. "
                "The endpoint must be publicly accessible."
            ),
        )

    if response.status_code != 200:
        return ValidationResult(
            is_valid=False,
            message=f"GET /entries returned unexpected status {response.status_code}.",
        )

    # Parse JSON response
    try:
        data = response.json()
    except json.JSONDecodeError:
        return ValidationResult(
            is_valid=False,
            message="GET /entries did not return valid JSON.",
        )

    # Must be an array
    if not isinstance(data, list):
        return ValidationResult(
            is_valid=False,
            message="GET /entries must return an array of entries.",
        )

    # Validate entries content
    result = _validate_entries_json(data)

    if result.is_valid:
        logger.info(
            "deployed_api.verified",
            extra={"url": base_url, "entries_count": len(data)},
        )

    return result
