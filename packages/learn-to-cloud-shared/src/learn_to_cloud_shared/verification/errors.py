"""Shared resilience primitives for verification services.

Centralises retriable exception types, exception classes, and
error-to-result mappers so every verification module draws from
a single source of truth.
"""

from __future__ import annotations

import logging

import httpx
from opentelemetry import metrics, trace

from learn_to_cloud_shared.schemas import ValidationResult

logger = logging.getLogger(__name__)

_meter = metrics.get_meter("learn_to_cloud")
# Low-cardinality counter for alerting on upstream/auth failures.
_GITHUB_API_ERROR_COUNTER = _meter.create_counter(
    name="github.api_error",
    description="GitHub API calls that failed with an auth, client, or server error",
    unit="{error}",
)


def _github_error_type(response: httpx.Response) -> str:
    status = response.status_code
    if status == 429 or (
        status == 403
        and (
            response.headers.get("x-ratelimit-remaining") == "0"
            or "retry-after" in response.headers
        )
    ):
        return "rate_limit"
    if status == 403:
        try:
            body = response.json()
        except ValueError:
            body = None
        if isinstance(body, dict):
            message = body.get("message")
            if isinstance(message, str) and (
                "rate limit" in message.lower() or "abuse detection" in message.lower()
            ):
                return "rate_limit"
    if status == 401:
        return "authentication"
    if status == 403:
        return "authorization"
    if status >= 500:
        return "provider_unavailable"
    return "client_error"


# ---------------------------------------------------------------------------
# Base retriable exceptions (httpx network / timeout errors)
# ---------------------------------------------------------------------------
BASE_RETRIABLE: tuple[type[Exception], ...] = (
    httpx.RequestError,
    httpx.TimeoutException,
)


def make_retriable(
    *extra: type[Exception],
) -> tuple[type[Exception], ...]:
    """Build a RETRIABLE_EXCEPTIONS tuple by appending service-specific types."""
    return BASE_RETRIABLE + extra


# ---------------------------------------------------------------------------
# Server error hierarchy
# ---------------------------------------------------------------------------
class VerificationError(Exception):
    """Base exception for verification failures.

    Attributes:
        retriable: ``True`` when the caller should retry (transient error).
    """

    def __init__(self, message: str, retriable: bool = False):
        super().__init__(message)
        self.retriable = retriable


class ServerError(Exception):
    """Base for retriable server-side errors across all services.

    Subclass per service so retry logic can
    distinguish which upstream failed.
    """

    def __init__(self, message: str, retry_after: float | None = None):
        super().__init__(message)
        self.retry_after = retry_after


class GitHubServerError(ServerError):
    """Raised when GitHub API returns a 5xx or 429 (retriable)."""


class DeployedApiServerError(ServerError):
    """Raised when deployed API returns a 5xx error (retriable)."""


# ---------------------------------------------------------------------------
# Error → ValidationResult mappers
# ---------------------------------------------------------------------------
def github_error_to_result(
    e: Exception,
    *,
    event: str,
) -> ValidationResult:
    """Map GitHub API exceptions to a user-facing ValidationResult.

    A 404 is a normal outcome (the learner pointed us at something that
    isn't there), so it stays quiet: span/result only, no warning log or
    metric. Auth/client errors (401/403), server errors (5xx), and transient
    network failures are operational problems that operators need to find
    across all users, so they emit a WARN log (severity, queryable) and bump
    the ``github.api_error`` counter (alertable) in addition to the span
    event.

    Args:
        e: The caught exception.
        event: Structured log event name (e.g. ``"pr_verification.api_error"``).
    """
    if isinstance(e, httpx.HTTPStatusError):
        status = e.response.status_code
        if status == 404:
            return ValidationResult(
                is_valid=False,
                message="Resource not found on GitHub. Check the URL and try again.",
            )
        span = trace.get_current_span()
        span.set_attribute("http.response.status_code", status)
        span.add_event(event, {"http.response.status_code": status})
        logger.warning(event, extra={"http.response.status_code": status})
        error_type = _github_error_type(e.response)
        _GITHUB_API_ERROR_COUNTER.add(1, {"error.type": error_type})
        return ValidationResult(
            is_valid=False,
            message=f"GitHub API error ({status}). Try again later.",
            verification_completed=False,
        )

    # RETRIABLE_EXCEPTIONS (RequestError, TimeoutException, etc.)
    error_type = type(e).__name__
    span = trace.get_current_span()
    span.set_attribute("error.type", error_type)
    span.add_event(event, {"error.type": error_type})
    logger.warning(event, extra={"error.type": error_type})
    _GITHUB_API_ERROR_COUNTER.add(1, {"error.type": "network"})
    return ValidationResult(
        is_valid=False,
        message="Could not reach GitHub. Please try again later.",
        verification_completed=False,
    )


def deployed_api_error_to_result(
    exc: Exception,
    *,
    step: str = "",
) -> ValidationResult:
    """Convert a deployed-API request exception into a ValidationResult.

    Centralises error handling for timeout, connection,
    and server errors that can occur during any HTTP call in the flow.
    """
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
        span.add_event(
            "deployed_api.server_error",
            {
                "error.type": "server_error",
                "verification.operation": step or "request",
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

    # Unexpected exception — re-raise so it's not silently swallowed
    raise exc  # pragma: no cover
