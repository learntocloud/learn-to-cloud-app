"""Clerk authentication utilities.

Provides:
- Clerk SDK client lifecycle management
- JWT verification with circuit breaker protection
- FastAPI dependencies for authenticated routes

Circuit Breaker:
- Opens after 5 consecutive JWKS infrastructure failures
- Fails fast for 60 seconds when open (returns None -> 401)
- Protects against Clerk outages blocking worker threads
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Annotated

from circuitbreaker import CircuitBreakerError, CircuitBreakerMonitor, circuit
from fastapi import Depends, HTTPException, Request

from core.config import get_settings
from core.logger import get_logger
from core.telemetry import (
    log_business_event,
    track_dependency,
)
from core.wide_event import set_wide_event_fields

if TYPE_CHECKING:
    from clerk_backend_api import Clerk
    from clerk_backend_api.security.types import (
        RequestState,
    )

logger = get_logger(__name__)

# Module-level singleton for the Clerk SDK client
_clerk_client: Clerk | None = None
_clerk_initialized: bool = False


def _get_jwks_failure_reasons() -> frozenset:
    """Build the set of JWKS failure reasons on first use (avoids eager import)."""
    from clerk_backend_api.security.types import TokenVerificationErrorReason

    return frozenset(
        {
            TokenVerificationErrorReason.JWK_FAILED_TO_LOAD,
            TokenVerificationErrorReason.JWK_REMOTE_INVALID,
            TokenVerificationErrorReason.JWK_FAILED_TO_RESOLVE,
            TokenVerificationErrorReason.JWK_KID_MISMATCH,
        }
    )


_JWKS_FAILURE_REASONS: frozenset | None = None

# Circuit breaker configuration
_CIRCUIT_NAME = "clerk_auth"
_CIRCUIT_FAILURE_THRESHOLD = 5  # Open after 5 failures
_CIRCUIT_RECOVERY_TIMEOUT = 60  # Try again after 60 seconds


class ClerkAuthUnavailable(Exception):
    """Raised when Clerk authentication infrastructure is unavailable.

    This exception triggers the circuit breaker when JWKS fetching fails,
    indicating Clerk infrastructure issues rather than user authentication errors.
    """

    def __init__(self, reason: object):
        self.reason = reason
        super().__init__(f"Clerk auth unavailable: {reason}")


def get_clerk_client() -> Clerk | None:
    return _clerk_client


def init_clerk_client() -> None:
    """Initialize Clerk SDK. Auth disabled if CLERK_SECRET_KEY not set."""
    global _clerk_client, _clerk_initialized, _JWKS_FAILURE_REASONS
    _clerk_initialized = True

    settings = get_settings()
    if not settings.clerk_secret_key:
        logger.warning(
            "CLERK_SECRET_KEY not configured - authentication disabled. "
            "All authenticated endpoints will return 401."
        )
        return

    from clerk_backend_api import Clerk as _Clerk

    _clerk_client = _Clerk(bearer_auth=settings.clerk_secret_key)
    _JWKS_FAILURE_REASONS = _get_jwks_failure_reasons()
    logger.info("Clerk SDK client initialized")


def _get_circuit_by_name(name: str):
    """Get a circuit breaker by name from the monitor."""
    for cb in CircuitBreakerMonitor.get_circuits():
        if cb.name == name:
            return cb
    return None


def close_clerk_client() -> None:
    """Clear Clerk client reference. SDK manages its own httpx lifecycle."""
    global _clerk_client
    _clerk_client = None


def _get_authorized_parties() -> list[str]:
    return get_settings().allowed_origins


@track_dependency("clerk_auth", "Auth")
@circuit(
    failure_threshold=_CIRCUIT_FAILURE_THRESHOLD,
    recovery_timeout=_CIRCUIT_RECOVERY_TIMEOUT,
    expected_exception=(ClerkAuthUnavailable,),
    name=_CIRCUIT_NAME,
)
def _authenticate_request_with_circuit_breaker(
    clerk: Clerk, req: Request, authorized_parties: list[str]
) -> RequestState:  # type: ignore[override]
    """Raises ClerkAuthUnavailable on JWKS failure (triggers circuit breaker)."""
    from clerk_backend_api.security.types import AuthenticateRequestOptions

    request_state = clerk.authenticate_request(
        req,
        AuthenticateRequestOptions(
            authorized_parties=authorized_parties,
        ),
    )

    # Check for JWKS infrastructure failures - raise to trigger circuit breaker
    if not request_state.is_signed_in:
        reason = getattr(request_state, "reason", None)
        if _JWKS_FAILURE_REASONS and reason in _JWKS_FAILURE_REASONS:
            raise ClerkAuthUnavailable(reason)

    return request_state


def get_user_id_from_request(req: Request) -> str | None:
    """Get authenticated user ID, or None.

    Note: Intentionally synchronous - JWT validation is CPU-bound (cached JWKS).
    """
    # Check if init was called - fail fast with clear error if not
    if not _clerk_initialized:
        set_wide_event_fields(
            auth_error="clerk_not_initialized",
        )
        return None

    clerk = get_clerk_client()
    if clerk is None:
        # Auth disabled (no secret key configured)
        # Logged once at startup, don't spam logs here
        return None

    authorized_parties = _get_authorized_parties()

    try:
        request_state = _authenticate_request_with_circuit_breaker(
            clerk, req, authorized_parties
        )
    except CircuitBreakerError:
        # Circuit is open - fail fast
        log_business_event("clerk_auth_circuit_rejected", 1, {"circuit": _CIRCUIT_NAME})
        return None
    except ClerkAuthUnavailable as e:
        # JWKS failure - already counted by circuit breaker
        set_wide_event_fields(
            auth_error="clerk_infrastructure_issue",
            auth_error_reason=str(e.reason),
        )
        return None

    if request_state.is_signed_in:
        if request_state.payload is not None:
            return request_state.payload.get("sub")
        return None

    # Not signed in - normal auth failure (invalid/expired token, etc.)
    # Don't log - this is expected for unauthenticated requests
    return None


def require_auth(request: Request) -> str:
    """Raises 401 if not authenticated. Sets request.state.user_id."""
    user_id = get_user_id_from_request(request)
    if not user_id:
        raise HTTPException(status_code=401, detail="Unauthorized")

    request.state.user_id = user_id
    set_wide_event_fields(user_id=user_id)
    return user_id


def optional_auth(request: Request) -> str | None:
    """Returns user_id or None. Does not raise."""
    user_id = get_user_id_from_request(request)
    if user_id:
        request.state.user_id = user_id
        set_wide_event_fields(user_id=user_id)
    return user_id


UserId = Annotated[str, Depends(require_auth)]
OptionalUserId = Annotated[str | None, Depends(optional_auth)]
