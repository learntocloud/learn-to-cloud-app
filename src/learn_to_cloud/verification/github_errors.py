"""GitHub response errors, learner results, and operational telemetry."""

from __future__ import annotations

import logging

import httpx2
from opentelemetry import trace

from learn_to_cloud.schemas.verification import ValidationResult
from learn_to_cloud.verification.errors import UpstreamResponseError

logger = logging.getLogger(__name__)


class GitHubServerError(UpstreamResponseError):
    """Raised when GitHub returns a retriable 5xx or 429 response."""


def _github_error_type(status: int, response: httpx2.Response | None = None) -> str:
    if status == 429:
        return "rate_limit"
    if status == 403 and response is not None:
        if (
            response.headers.get("x-ratelimit-remaining") == "0"
            or "retry-after" in response.headers
        ):
            return "rate_limit"
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


def github_error_to_result(e: Exception, *, event: str) -> ValidationResult:
    """Map supported GitHub failures once, keeping missing resources quiet."""
    status: int | None = None
    response: httpx2.Response | None = None
    if isinstance(e, GitHubServerError):
        status = e.status_code
    elif isinstance(e, httpx2.HTTPStatusError):
        response = e.response
        status = response.status_code
    elif not isinstance(e, httpx2.RequestError):
        raise e

    if status == 404:
        return ValidationResult(
            is_valid=False,
            message="Resource not found on GitHub. Check the URL and try again.",
        )

    error_code = (
        _github_error_type(status, response) if status is not None else "network"
    )
    error_type = error_code if status is not None else type(e).__qualname__
    attributes: dict[str, str | int] = {"error.type": error_type}
    if status is not None:
        attributes["http.response.status_code"] = status
    span = trace.get_current_span()
    for key, value in attributes.items():
        span.set_attribute(key, value)
    span.add_event(event, attributes)
    logger.warning(event, extra=attributes)
    return ValidationResult(
        is_valid=False,
        message=(
            f"GitHub API error ({status}). Try again later."
            if status is not None
            else "Could not reach GitHub. Please try again later."
        ),
        verification_completed=False,
        error_code=error_code,
    )
