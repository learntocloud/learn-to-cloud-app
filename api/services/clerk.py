"""Clerk authentication service for user data synchronization."""

import logging
import time
from dataclasses import dataclass

import httpx

from core.config import get_settings

logger = logging.getLogger(__name__)

_http_client: httpx.AsyncClient | None = None

_clerk_lookup_backoff_until: dict[str, float] = {}
_CLERK_LOOKUP_BACKOFF_SECONDS = 300.0


def _cleanup_expired_backoffs() -> None:
    """Remove expired backoff entries to prevent unbounded memory growth."""
    now = time.time()
    expired = [k for k, v in _clerk_lookup_backoff_until.items() if v <= now]
    for k in expired:
        del _clerk_lookup_backoff_until[k]


async def get_http_client() -> httpx.AsyncClient:
    """Get or create a reusable HTTP client with connection pooling."""
    global _http_client
    if _http_client is None or _http_client.is_closed:
        settings = get_settings()
        _http_client = httpx.AsyncClient(
            timeout=settings.http_timeout,
            limits=httpx.Limits(max_connections=20, max_keepalive_connections=10),
        )
    return _http_client


async def close_http_client() -> None:
    """Close the reusable HTTP client (called on application shutdown)."""
    global _http_client
    if _http_client is None:
        return
    if not _http_client.is_closed:
        await _http_client.aclose()
    _http_client = None


@dataclass
class ClerkUserData:
    """Data fetched from Clerk API for a user."""

    email: str | None = None
    first_name: str | None = None
    last_name: str | None = None
    avatar_url: str | None = None
    github_username: str | None = None


def extract_github_username(data: dict) -> str | None:
    """Extract GitHub username from Clerk webhook/API data.

    Clerk stores OAuth account info in 'external_accounts' array.
    Each account has 'provider' and 'username' fields.
    """
    external_accounts = data.get("external_accounts", [])

    return next(
        (
            account.get("username") or account.get("provider_user_id")
            for account in external_accounts
            if account.get("provider") in ("github", "oauth_github")
            and (account.get("username") or account.get("provider_user_id"))
        ),
        None,
    )


def extract_primary_email(data: dict, fallback: str | None = None) -> str | None:
    """Extract primary email from Clerk webhook/API data."""
    email_addresses = data.get("email_addresses", [])
    return next(
        (
            e.get("email_address")
            for e in email_addresses
            if e.get("id") == data.get("primary_email_address_id")
        ),
        email_addresses[0].get("email_address") if email_addresses else fallback,
    )


async def fetch_user_data(user_id: str) -> ClerkUserData | None:
    """Fetch full user data from Clerk API.

    This is used when the user doesn't have complete profile data stored.
    Returns avatar_url (which comes from GitHub if using GitHub OAuth),
    name, email, and github_username.
    """
    settings = get_settings()
    if not settings.clerk_secret_key:
        return None

    _cleanup_expired_backoffs()

    now = time.time()
    backoff_until = _clerk_lookup_backoff_until.get(user_id)
    if backoff_until is not None and backoff_until > now:
        return None

    try:
        client = await get_http_client()
        response = await client.get(
            f"https://api.clerk.com/v1/users/{user_id}",
            headers={
                "Authorization": f"Bearer {settings.clerk_secret_key}",
                "Content-Type": "application/json",
            },
        )

        if response.status_code != 200:
            logger.warning(f"Failed to fetch user from Clerk: {response.status_code}")
            return None

        data = response.json()

        return ClerkUserData(
            email=extract_primary_email(data),
            first_name=data.get("first_name"),
            last_name=data.get("last_name"),
            avatar_url=data.get("image_url"),
            github_username=extract_github_username(data),
        )
    except Exception as e:
        _clerk_lookup_backoff_until[user_id] = (
            time.time() + _CLERK_LOOKUP_BACKOFF_SECONDS
        )
        logger.warning(f"Error fetching user data from Clerk: {e}")
        return None


async def fetch_github_username(user_id: str) -> str | None:
    """Fetch GitHub username directly from Clerk API.

    This is used when the user doesn't have a github_username stored.
    """
    clerk_data = await fetch_user_data(user_id)
    return clerk_data.github_username if clerk_data else None
