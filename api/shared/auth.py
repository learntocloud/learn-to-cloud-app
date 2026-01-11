"""Clerk authentication utilities."""

import httpx
from fastapi import Request
from clerk_backend_api import Clerk, authenticate_request, AuthenticateRequestOptions

from .config import get_settings


settings = get_settings()


def get_clerk_client() -> Clerk:
    """Get Clerk client instance."""
    return Clerk(bearer_auth=settings.clerk_secret_key)


def get_user_id_from_request(req: Request) -> str | None:
    """
    Get the authenticated user ID from the request.
    Returns None if not authenticated.
    """
    if not settings.clerk_secret_key:
        return None
    
    httpx_request = httpx.Request(
        method=req.method,
        url=str(req.url),
        headers=dict(req.headers),
    )
    
    # Get frontend URL from env or use default
    frontend_url = settings.frontend_url
    
    # Build authorized parties list
    authorized_parties = [
        frontend_url,
        "http://localhost:3000",
        "http://localhost:4280",
    ]
    
    # Add Azure Container Apps domains
    if ".azurecontainerapps.io" in frontend_url:
        authorized_parties.append(frontend_url)
    
    try:
        request_state = authenticate_request(
            httpx_request,
            AuthenticateRequestOptions(
                secret_key=settings.clerk_secret_key,
                authorized_parties=authorized_parties,
            )
        )
        
        if not request_state.is_signed_in:
            return None
        
        return request_state.payload.get("sub")
        
    except Exception:
        return None
