"""Clerk authentication utilities."""

import logging
from typing import Annotated

import httpx
from clerk_backend_api import Clerk
from clerk_backend_api.security.types import AuthenticateRequestOptions
from fastapi import Depends, HTTPException, Request

from .config import get_settings

logger = logging.getLogger(__name__)

def _get_authorized_parties() -> list[str]:
    """Get authorized parties for Clerk authentication from centralized config."""
    return get_settings().allowed_origins

def get_user_id_from_request(req: Request) -> str | None:
    """
    Get the authenticated user ID from the request.
    Returns None if not authenticated.
    """
    settings = get_settings()

    if not settings.clerk_secret_key:
        logger.warning("No CLERK_SECRET_KEY configured")
        return None

    auth_header = req.headers.get("authorization", "")
    logger.info(
        f"Auth header present: {bool(auth_header)}, starts with Bearer: {auth_header.startswith('Bearer ')}"
    )

    httpx_request = httpx.Request(
        method=req.method,
        url=str(req.url),
        headers=dict(req.headers),
    )

    try:
        authorized_parties = _get_authorized_parties()
        logger.info(f"Authorized parties: {authorized_parties}")

        with Clerk(bearer_auth=settings.clerk_secret_key) as clerk:
            request_state = clerk.authenticate_request(
                httpx_request,
                AuthenticateRequestOptions(
                    authorized_parties=authorized_parties,
                ),
            )

            logger.info(f"Clerk auth result: is_signed_in={request_state.is_signed_in}")

            if not request_state.is_signed_in:
                logger.info(
                    f"Not signed in. Reason: {getattr(request_state, 'reason', 'unknown')}, message: {getattr(request_state, 'message', 'none')}"
                )
                return None

            if request_state.payload is None:
                logger.info("Payload is None")
                return None

            user_id = request_state.payload.get("sub")
            logger.info(f"Authenticated user: {user_id}")
            return user_id

    except Exception as e:
        logger.exception(f"Failed to authenticate request: {e}")
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
