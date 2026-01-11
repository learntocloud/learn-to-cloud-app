"""Clerk authentication utilities."""

import logging

import httpx
from clerk_backend_api import Clerk
from clerk_backend_api.security.types import AuthenticateRequestOptions
from fastapi import Request

from .config import get_settings

logger = logging.getLogger(__name__)


def _build_authorized_parties() -> list[str]:
    """Build list of authorized parties for Clerk authentication."""
    settings = get_settings()
    
    parties = {
        "http://localhost:3000",
        "http://localhost:4280",
    }
    
    if settings.frontend_url:
        parties.add(settings.frontend_url)
    
    return list(parties)


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
                    authorized_parties=_build_authorized_parties(),
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
