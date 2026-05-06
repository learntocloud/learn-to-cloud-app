"""Shared resilience primitives for verification services.

Centralises retriable exception types, exception classes, and
error-to-result mappers so every verification module draws from
a single source of truth.
"""

from __future__ import annotations

import httpx
from opentelemetry import trace
from opentelemetry.util.types import AttributeValue

from learn_to_cloud_shared.schemas import ValidationResult

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
    context: dict[str, AttributeValue],
) -> ValidationResult:
    """Map GitHub API exceptions to a user-facing ValidationResult.

    Args:
        e: The caught exception.
        event: Structured log event name (e.g. ``"pr_verification.api_error"``).
        context: Extra fields for structured logging (owner, repo, pr, etc.).
    """
    if isinstance(e, httpx.HTTPStatusError):
        if e.response.status_code == 404:
            return ValidationResult(
                is_valid=False,
                message="Resource not found on GitHub. Check the URL and try again.",
            )
        span = trace.get_current_span()
        span.add_event(event, {**context, "status": e.response.status_code})
        return ValidationResult(
            is_valid=False,
            message=f"GitHub API error ({e.response.status_code}). Try again later.",
            verification_completed=False,
        )

    # RETRIABLE_EXCEPTIONS (RequestError, TimeoutException, etc.)
    span = trace.get_current_span()
    span.add_event(event, {**context, "error": str(e)})
    return ValidationResult(
        is_valid=False,
        message="Could not reach GitHub. Please try again later.",
        verification_completed=False,
    )


def deployed_api_error_to_result(
    exc: Exception,
    entries_url: str,
    *,
    step: str = "",
) -> ValidationResult:
    """Convert a deployed-API request exception into a ValidationResult.

    Centralises error handling for timeout, connection,
    and server errors that can occur during any HTTP call in the flow.
    """
    step_prefix = f"{step}: " if step else ""

    if isinstance(exc, httpx.TimeoutException):
        span = trace.get_current_span()
        span.add_event("deployed_api_timeout", {"url": entries_url, "step": step})
        return ValidationResult(
            is_valid=False,
            message=(
                f"{step_prefix}Request timed out. Ensure your API is accessible "
                "and responding quickly."
            ),
        )

    if isinstance(exc, DeployedApiServerError):
        span = trace.get_current_span()
        span.add_event(
            "deployed_api_server_error",
            {"url": entries_url, "error": str(exc), "step": step},
        )
        return ValidationResult(
            is_valid=False,
            message=(
                f"{step_prefix}Your API returned a server error (5xx). "
                "Please check your deployment."
            ),
        )

    if isinstance(exc, httpx.RequestError):
        span = trace.get_current_span()
        span.add_event(
            "deployed_api_request_error",
            {"url": entries_url, "error": str(exc), "step": step},
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
