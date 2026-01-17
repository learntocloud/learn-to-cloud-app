"""Rate limiting configuration using slowapi.

SCALABILITY NOTES:
- Production MUST use Redis: set RATELIMIT_STORAGE_URI="redis://host:port/db"
- memory:// storage does NOT work with multiple workers/replicas
- Each replica maintains separate counters, effectively multiplying limits by N
"""

import logging

from fastapi import Request, Response
from slowapi import Limiter
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address
from starlette.responses import JSONResponse

from core.config import get_settings

logger = logging.getLogger(__name__)

settings = get_settings()

# Validate storage configuration in non-development environments
if (
    settings.environment != "development"
    and settings.ratelimit_storage_uri == "memory://"
):
    logger.warning(
        "SECURITY WARNING: Using in-memory rate limiting in %s environment. "
        "This does NOT work correctly with multiple workers/replicas. "
        "Set RATELIMIT_STORAGE_URI to a Redis URL for distributed rate limiting.",
        settings.environment,
    )


def _get_request_identifier(request: Request) -> str:
    """
    Get a unique identifier for rate limiting.

    Uses authenticated user ID if available, otherwise falls back to IP address.
    This prevents a single user from bypassing limits by using multiple IPs,
    while still protecting against unauthenticated abuse.

    NOTE: user_id availability depends on auth middleware execution order.
    For pre-auth endpoints, this will fall back to IP-based limiting.
    """
    if hasattr(request.state, "user_id") and request.state.user_id:
        return f"user:{request.state.user_id}"

    return get_remote_address(request)


# Determine if we should enable in-memory fallback (only when using Redis)
_using_redis = settings.ratelimit_storage_uri.startswith("redis://")

limiter = Limiter(
    key_func=_get_request_identifier,
    default_limits=["100/minute"],
    storage_uri=settings.ratelimit_storage_uri,
    # Enable graceful fallback to memory when Redis is temporarily unavailable
    # This prevents complete outage but logs warnings about degraded limiting
    in_memory_fallback_enabled=_using_redis,
    # Add key prefix to avoid collisions if sharing Redis with other services
    key_prefix="ltc:",
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


EXTERNAL_API_LIMIT = "10/minute"

WEBHOOK_LIMIT = "60/minute"

AUTH_LIMIT = "20/minute"
