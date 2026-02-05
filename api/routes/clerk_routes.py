"""Clerk Frontend API proxy routes.

Proxies requests from /.clerk/* to Clerk's Frontend API.
Required when using Azure Static Web Apps with the default hostname
since you can't add CNAME records for *.azurestaticapps.net domains.

See: https://clerk.com/docs/guides/dashboard/dns-domains/proxy-fapi
"""

import asyncio
import os

import httpx
from fastapi import APIRouter, HTTPException, Request, Response

router = APIRouter(prefix="/api/.clerk", tags=["clerk"])

# Shared HTTP client for Clerk FAPI proxy (connection pooling)
_clerk_proxy_client: httpx.AsyncClient | None = None
_clerk_proxy_client_lock = asyncio.Lock()


async def _get_clerk_proxy_client() -> httpx.AsyncClient:
    """Get or create a shared HTTP client for Clerk FAPI proxy requests."""
    global _clerk_proxy_client
    if _clerk_proxy_client is not None and not _clerk_proxy_client.is_closed:
        return _clerk_proxy_client

    async with _clerk_proxy_client_lock:
        if _clerk_proxy_client is not None and not _clerk_proxy_client.is_closed:
            return _clerk_proxy_client

        _clerk_proxy_client = httpx.AsyncClient(
            timeout=30.0,
            limits=httpx.Limits(max_connections=20, max_keepalive_connections=10),
        )
        return _clerk_proxy_client


async def close_clerk_proxy_client() -> None:
    """Close the shared Clerk proxy HTTP client (called on application shutdown)."""
    global _clerk_proxy_client
    if _clerk_proxy_client is not None and not _clerk_proxy_client.is_closed:
        await _clerk_proxy_client.aclose()
    _clerk_proxy_client = None


def _get_clerk_fapi_base() -> str:
    """Resolve the Clerk Frontend API base URL from env."""
    return (
        os.getenv("CLERK_FAPI_BASE")
        or os.getenv("CLERK_FAPI")
        or os.getenv("CLERK_FRONTEND_API")
        or ""
    )


@router.api_route(
    "/{path:path}",
    methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS", "HEAD"],
    include_in_schema=False,
)
async def clerk_proxy(request: Request, path: str) -> Response:
    """Proxy requests to Clerk's Frontend API.

    This allows Clerk authentication to work without custom domain DNS setup.
    All requests to /.clerk/* are forwarded to Clerk's FAPI.
    """
    clerk_fapi_base = _get_clerk_fapi_base().rstrip("/")
    if not clerk_fapi_base:
        raise HTTPException(
            status_code=500,
            detail="CLERK_FAPI_BASE is not configured",
        )

    # Build target URL
    target_url = f"{clerk_fapi_base}/{path}"
    if request.url.query:
        target_url = f"{target_url}?{request.url.query}"

    # Get request body if present
    body = await request.body()

    # Forward headers, excluding hop-by-hop headers
    headers = {
        key: value
        for key, value in request.headers.items()
        if key.lower()
        not in (
            "host",
            "connection",
            "keep-alive",
            "transfer-encoding",
            "te",
            "trailer",
            "upgrade",
        )
    }

    client = await _get_clerk_proxy_client()
    response = await client.request(
        method=request.method,
        url=target_url,
        headers=headers,
        content=body,
    )

    # Build response, excluding hop-by-hop headers
    response_headers = {
        key: value
        for key, value in response.headers.items()
        if key.lower()
        not in (
            "connection",
            "keep-alive",
            "transfer-encoding",
            "te",
            "trailer",
            "upgrade",
            "content-encoding",  # Let FastAPI handle encoding
            "content-length",  # Will be recalculated
        )
    }

    return Response(
        content=response.content,
        status_code=response.status_code,
        headers=response_headers,
        media_type=response.headers.get("content-type"),
    )
