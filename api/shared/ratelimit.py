"""Rate limiting configuration using slowapi."""

import logging

from fastapi import Request, Response
from slowapi import Limiter
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address
from starlette.responses import JSONResponse

logger = logging.getLogger(__name__)


def _get_request_identifier(request: Request) -> str:
    """
    Get a unique identifier for rate limiting.

    Uses authenticated user ID if available, otherwise falls back to IP address.
    This prevents a single user from bypassing limits by using multiple IPs,
    while still protecting against unauthenticated abuse.
    """
    # Check if user is authenticated (set by auth dependency)
    if hasattr(request.state, "user_id") and request.state.user_id:
        return f"user:{request.state.user_id}"

    # Fall back to IP address for unauthenticated requests
    return get_remote_address(request)


# Create the limiter instance with in-memory storage
# For single-replica deployments, in-memory is sufficient and avoids Redis costs
limiter = Limiter(
    key_func=_get_request_identifier,
    default_limits=["100/minute"],  # Default rate limit for all endpoints
    storage_uri="memory://",
)


def rate_limit_exceeded_handler(request: Request, exc: RateLimitExceeded) -> Response:
    """Custom handler for rate limit exceeded errors."""
    logger.warning(
        f"Rate limit exceeded for {_get_request_identifier(request)}: {exc.detail}"
    )
    return JSONResponse(
        status_code=429,
        content={
            "detail": "Rate limit exceeded. Please slow down.",
            "retry_after": exc.detail,
        },
        headers={"Retry-After": str(getattr(exc, "retry_after", 60))},
    )


# Specific rate limits for different endpoint types
# Use these as decorators on routes that need custom limits

# For endpoints that make external API calls (GitHub validation, etc.)
EXTERNAL_API_LIMIT = "10/minute"

# For webhook endpoints (should be more permissive for legitimate webhook traffic)
WEBHOOK_LIMIT = "60/minute"

# For authentication-related endpoints
AUTH_LIMIT = "20/minute"
