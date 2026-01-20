"""Rate limiting configuration using slowapi.

NOTE: In-memory storage only works for single-replica deployments.
Each replica maintains separate counters—multiple replicas effectively
multiply the rate limits by the number of replicas.
"""

from fastapi import Request, Response
from slowapi import Limiter
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address
from starlette.responses import JSONResponse

from core.config import get_settings
from core.logger import get_logger

logger = get_logger(__name__)

settings = get_settings()


def _get_request_identifier(request: Request) -> str:
    # Uses user_id if authenticated, otherwise IP address
    if hasattr(request.state, "user_id") and request.state.user_id:
        return f"user:{request.state.user_id}"
    return get_remote_address(request)


limiter = Limiter(
    key_func=_get_request_identifier,
    default_limits=["100/minute"],
    storage_uri=settings.ratelimit_storage_uri,
)


def rate_limit_exceeded_handler(request: Request, exc: RateLimitExceeded) -> Response:
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
