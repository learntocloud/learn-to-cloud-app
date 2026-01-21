"""Clerk Frontend API proxy routes.

Proxies requests from /.clerk/* to Clerk's Frontend API.
Required when using Azure Static Web Apps with the default hostname
since you can't add CNAME records for *.azurestaticapps.net domains.

See: https://clerk.com/docs/guides/dashboard/dns-domains/proxy-fapi
"""

import httpx
from fastapi import APIRouter, Request, Response

router = APIRouter(tags=["clerk"])

# Clerk Frontend API base URL - derived from publishable key
# pk_test_xxx.clerk.accounts.dev -> xxx.clerk.accounts.dev
# pk_live_xxx.clerk.accounts.dev -> xxx.clerk.accounts.dev
CLERK_FAPI_BASE = "https://ample-kite-60.clerk.accounts.dev"


@router.api_route(
    "/.clerk/{path:path}",
    methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS", "HEAD"],
    include_in_schema=False,
)
async def clerk_proxy(request: Request, path: str) -> Response:
    """Proxy requests to Clerk's Frontend API.

    This allows Clerk authentication to work without custom domain DNS setup.
    All requests to /.clerk/* are forwarded to Clerk's FAPI.
    """
    # Build target URL
    target_url = f"{CLERK_FAPI_BASE}/{path}"
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

    async with httpx.AsyncClient(timeout=30.0) as client:
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
