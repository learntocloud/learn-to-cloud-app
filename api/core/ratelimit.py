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


def _get_request_identifier(request: Request) -> str:
    if hasattr(request.state, "user_id") and request.state.user_id:
        return f"user:{request.state.user_id}"
    return get_remote_address(request)


limiter = Limiter(
    key_func=_get_request_identifier,
    default_limits=["100/minute"],
    storage_uri=get_settings().ratelimit_storage_uri,
)


def rate_limit_exceeded_handler(request: Request, exc: Exception) -> Response:
    if not isinstance(exc, RateLimitExceeded):
        return JSONResponse(status_code=500, content={"detail": "Unexpected error"})

    return JSONResponse(
        status_code=429,
        content={
            "detail": "Rate limit exceeded. Please slow down.",
            "retry_after": exc.detail,
        },
        headers={"Retry-After": str(getattr(exc, "retry_after", 60))},
    )
