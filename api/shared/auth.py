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
        return None
    
    httpx_request = httpx.Request(
        method=req.method,
        url=str(req.url),
        headers=dict(req.headers),
    )
    
    try:
        with Clerk(bearer_auth=settings.clerk_secret_key) as clerk:
            request_state = clerk.authenticate_request(
                httpx_request,
                AuthenticateRequestOptions(
                    authorized_parties=_get_authorized_parties(),
                )
            )
            
            if not request_state.is_signed_in:
                return None
            
            if request_state.payload is None:
                return None
            
            return request_state.payload.get("sub")
        
    except Exception:
        logger.exception("Failed to authenticate request")
        return None


def require_auth(request: Request) -> str:
    """
    FastAPI dependency that requires authentication.
    
    Raises HTTPException 401 if not authenticated.
    
    Usage:
        @app.get("/protected")
        async def protected_route(user_id: UserId):
            return {"user_id": user_id}
    """
    user_id = get_user_id_from_request(request)
    if not user_id:
        raise HTTPException(status_code=401, detail="Unauthorized")
    return user_id


# Type alias for cleaner dependency injection in routes
UserId = Annotated[str, Depends(require_auth)]
