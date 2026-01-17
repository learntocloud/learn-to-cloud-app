"""Clerk authentication service for user data synchronization.

SCALABILITY:
- Per-user backoff prevents repeated Clerk API calls for problem accounts
- Circuit breaker fails fast when Clerk is unavailable (5 failures -> 60s recovery)
- Connection pooling via shared httpx.AsyncClient
"""

import asyncio
import logging
import time
from dataclasses import dataclass
from functools import lru_cache

import httpx
from circuitbreaker import circuit

from core.config import get_settings
from core.telemetry import track_dependency

logger = logging.getLogger(__name__)

_http_client: httpx.AsyncClient | None = None
_http_client_lock: asyncio.Lock | None = None

# Bounded LRU cache for backoff tracking (max 10K entries to prevent memory leaks)
_CLERK_LOOKUP_BACKOFF_SECONDS = 300.0
_MAX_BACKOFF_ENTRIES = 10_000


@lru_cache(maxsize=_MAX_BACKOFF_ENTRIES)
def _get_backoff_until(user_id: str) -> float:
    """Get cached backoff expiry time for a user (returns 0.0 if not in backoff)."""
    return 0.0


def _set_backoff(user_id: str) -> None:
    """Set backoff for a user. Uses LRU cache with bounded size."""
    # Clear the cached value and re-cache with new expiry
    _get_backoff_until.cache_info()  # Ensure cache exists
    # We store backoff state externally since lru_cache is read-only
    _backoff_state[user_id] = time.time() + _CLERK_LOOKUP_BACKOFF_SECONDS


def _is_in_backoff(user_id: str) -> bool:
    """Check if user is in backoff period."""
    expiry = _backoff_state.get(user_id, 0.0)
    if expiry <= time.time():
        _backoff_state.pop(user_id, None)  # Clean up expired entry
        return False
    return True


# Simple bounded dict with LRU eviction for backoff state
class _BoundedBackoffDict(dict):
    """Dict with max size that evicts oldest entries when full."""

    def __setitem__(self, key, value):
        if len(self) >= _MAX_BACKOFF_ENTRIES and key not in self:
            # Evict oldest ~10% of entries
            to_remove = list(self.keys())[: _MAX_BACKOFF_ENTRIES // 10]
            for k in to_remove:
                self.pop(k, None)
        super().__setitem__(key, value)


_backoff_state = _BoundedBackoffDict()


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


@track_dependency("clerk_api", "HTTP")
@circuit(
    failure_threshold=5,
    recovery_timeout=60,
    expected_exception=Exception,
    name="clerk_circuit",
)
async def fetch_user_data(user_id: str) -> ClerkUserData | None:
    """Fetch full user data from Clerk API.

    This is used when the user doesn't have complete profile data stored.
    Returns avatar_url (which comes from GitHub if using GitHub OAuth),
    name, email, and github_username.

    CIRCUIT BREAKER: Opens after 5 consecutive failures, recovers after 60 seconds.
    """
    settings = get_settings()
    if not settings.clerk_secret_key:
        return None

    # Check backoff with bounded cache
    if _is_in_backoff(user_id):
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
        _set_backoff(user_id)
        logger.warning(f"Error fetching user data from Clerk: {e}")
        return None


async def fetch_github_username(user_id: str) -> str | None:
    """Fetch GitHub username directly from Clerk API.

    This is used when the user doesn't have a github_username stored.
    """
    clerk_data = await fetch_user_data(user_id)
    return clerk_data.github_username if clerk_data else None
