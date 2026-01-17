"""Clerk authentication utilities."""

import logging
import time
from typing import Annotated

from clerk_backend_api import Clerk
from clerk_backend_api.security.types import (
    AuthenticateRequestOptions,
    TokenVerificationErrorReason,
)
from fastapi import Depends, HTTPException, Request

from core.config import get_settings

logger = logging.getLogger(__name__)

# Module-level singleton for the Clerk SDK client
_clerk_client: Clerk | None = None
_clerk_initialized: bool = False

# JWKS-related failure reasons that indicate infrastructure issues (not user error)
_JWKS_FAILURE_REASONS = frozenset(
    {
        TokenVerificationErrorReason.JWK_FAILED_TO_LOAD,
        TokenVerificationErrorReason.JWK_REMOTE_INVALID,
        TokenVerificationErrorReason.JWK_FAILED_TO_RESOLVE,
        TokenVerificationErrorReason.JWK_KID_MISMATCH,
    }
)

# Rate-limiting for JWKS failure warnings (avoid log spam during incidents)
_last_jwks_warning_time: float = 0.0
_JWKS_WARNING_INTERVAL_SECONDS: float = 60.0  # Log at most once per minute


def get_clerk_client() -> Clerk | None:
    """
    Get the singleton Clerk SDK client instance.

    Returns None if not initialized (auth disabled).
    """
    return _clerk_client


def init_clerk_client() -> None:
    """
    Initialize the Clerk SDK client (called on application startup).

    Should be called once during app lifespan startup.
    If CLERK_SECRET_KEY is not configured, auth will be disabled.
    """
    global _clerk_client, _clerk_initialized
    _clerk_initialized = True

    settings = get_settings()
    if not settings.clerk_secret_key:
        logger.warning(
            "CLERK_SECRET_KEY not configured - authentication disabled. "
            "All authenticated endpoints will return 401."
        )
        return

    _clerk_client = Clerk(bearer_auth=settings.clerk_secret_key)
    logger.info("Clerk SDK client initialized")


def close_clerk_client() -> None:
    """
    Close the Clerk SDK client (called on application shutdown).

    Note: The Clerk SDK manages its own httpx client lifecycle.
    We just clear our reference to allow garbage collection.
    """
    global _clerk_client
    _clerk_client = None


def _get_authorized_parties() -> list[str]:
    """Get authorized parties for Clerk authentication from centralized config."""
    return get_settings().allowed_origins


def get_user_id_from_request(req: Request) -> str | None:
    """
    Get the authenticated user ID from the request.
    Returns None if not authenticated.

    Note: This is intentionally synchronous. Clerk's authenticate_request()
    is CPU-bound JWT validation (cached JWKS). The rare JWKS fetch on cache
    miss is acceptable - it's infrequent (every 5 min per key ID) and the
    SDK handles retries internally.

    WARNING: The Clerk SDK's JWKS fetch has aggressive retries (up to 100)
    with no timeout configuration. During Clerk outages, this could block
    worker threads for extended periods. Monitor for JWKS failure warnings.
    """
    global _last_jwks_warning_time

    # Check if init was called - fail fast with clear error if not
    if not _clerk_initialized:
        logger.error(
            "Auth called before init_clerk_client() - this is a bug. "
            "Ensure init_clerk_client() is called during app startup."
        )
        return None

    clerk = get_clerk_client()
    if clerk is None:
        # Auth disabled (no secret key configured)
        # Logged once at startup, don't spam logs here
        return None

    authorized_parties = _get_authorized_parties()

    # FastAPI Request satisfies Clerk's Requestish protocol (has .headers Mapping)
    request_state = clerk.authenticate_request(
        req,
        AuthenticateRequestOptions(
            authorized_parties=authorized_parties,
        ),
    )

    if request_state.is_signed_in:
        if request_state.payload is not None:
            return request_state.payload.get("sub")
        return None

    # Not signed in - check reason for operational visibility
    reason = getattr(request_state, "reason", None)

    # Log JWKS failures as warnings (infrastructure issue, not user error)
    # Rate-limited to avoid log spam during incidents
    if reason in _JWKS_FAILURE_REASONS:
        now = time.monotonic()
        if now - _last_jwks_warning_time >= _JWKS_WARNING_INTERVAL_SECONDS:
            _last_jwks_warning_time = now
            logger.warning(
                "Auth infrastructure issue: %s (rate-limited warning)",
                reason,
            )

    return None


def require_auth(request: Request) -> str:
    """
    FastAPI dependency that requires authentication.

    Raises HTTPException 401 if not authenticated.
    Also sets request.state.user_id for rate limiting identification.

    Usage:
        @app.get("/protected")
        async def protected_route(user_id: UserId):
            return {"user_id": user_id}
    """
    user_id = get_user_id_from_request(request)
    if not user_id:
        raise HTTPException(status_code=401, detail="Unauthorized")

    request.state.user_id = user_id
    return user_id


def optional_auth(request: Request) -> str | None:
    """
    FastAPI dependency that provides optional authentication.

    Returns None if not authenticated, user_id otherwise.
    Does not raise exceptions.

    Usage:
        @app.get("/optional-protected")
        async def route(user_id: OptionalUserId = None):
            if user_id:
                return {"user_id": user_id}
            return {"user_id": None}
    """
    user_id = get_user_id_from_request(request)
    if user_id:
        request.state.user_id = user_id
    return user_id


UserId = Annotated[str, Depends(require_auth)]
OptionalUserId = Annotated[str | None, Depends(optional_auth)]
