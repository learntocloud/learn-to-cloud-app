"""Clerk authentication service for user data synchronization.

SCALABILITY:
- Per-user backoff prevents repeated Clerk API calls for problem accounts
- Circuit breaker fails fast when Clerk is unavailable (5 failures -> 60s recovery)
- Retry with exponential backoff for transient failures (3 attempts)
- Connection pooling via shared httpx.AsyncClient
"""

import asyncio
import logging
import time
from dataclasses import dataclass

import httpx
from circuitbreaker import circuit
from tenacity import (
    RetryCallState,
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential_jitter,
)

from core.config import get_settings
from core.telemetry import track_dependency

logger = logging.getLogger(__name__)

_http_client: httpx.AsyncClient | None = None
_http_client_lock: asyncio.Lock | None = None

# Bounded dict for backoff tracking (max 10K entries to prevent memory leaks)
_CLERK_LOOKUP_BACKOFF_SECONDS = 300.0
_MAX_BACKOFF_ENTRIES = 10_000


class ClerkServerError(Exception):
    """Raised when Clerk API returns a 5xx error or 429 (retriable)."""

    def __init__(self, message: str, retry_after: float | None = None):
        super().__init__(message)
        self.retry_after = retry_after


def _parse_retry_after(header_value: str | None) -> float | None:
    """Parse Retry-After header (seconds or HTTP date) into seconds."""
    if not header_value:
        return None
    try:
        # Try parsing as seconds first
        return float(header_value)
    except ValueError:
        pass
    # Could parse HTTP date here, but Clerk typically uses seconds
    return None


def _wait_with_retry_after(retry_state: RetryCallState) -> float:
    """Custom wait that respects Retry-After header.

    Falls back to exponential backoff with jitter if no Retry-After.
    """
    # Check if the exception has a retry_after value
    exc = retry_state.outcome.exception() if retry_state.outcome else None
    if isinstance(exc, ClerkServerError) and exc.retry_after:
        # Cap at 60s to avoid pathological values
        return min(exc.retry_after, 60.0)

    # Fall back to exponential backoff with jitter
    return wait_exponential_jitter(initial=0.5, max=4)(retry_state)


def _set_backoff(user_id: str) -> None:
    """Set backoff for a user. Uses bounded dict with LRU-style eviction."""
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


# Exceptions that should trigger retry and circuit breaker
RETRIABLE_EXCEPTIONS: tuple[type[Exception], ...] = (
    httpx.RequestError,
    httpx.TimeoutException,
    ClerkServerError,
)


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
    expected_exception=RETRIABLE_EXCEPTIONS,
    name="clerk_circuit",
)
@retry(
    retry=retry_if_exception_type(RETRIABLE_EXCEPTIONS),
    stop=stop_after_attempt(3),
    wait=_wait_with_retry_after,
    reraise=True,
)
async def _fetch_user_data_with_retry(user_id: str) -> ClerkUserData | None:
    """Internal: Fetch user data with retry logic. Use fetch_user_data() instead."""
    settings = get_settings()

    client = await get_http_client()
    response = await client.get(
        f"https://api.clerk.com/v1/users/{user_id}",
        headers={
            "Authorization": f"Bearer {settings.clerk_secret_key}",
            "Content-Type": "application/json",
        },
    )

    # 5xx errors are retriable - raise to trigger retry/circuit breaker
    if response.status_code >= 500:
        raise ClerkServerError(f"Clerk API returned {response.status_code}")

    # 429 rate limit is retriable
    if response.status_code == 429:
        retry_after = _parse_retry_after(response.headers.get("Retry-After"))
        raise ClerkServerError(
            "Clerk API rate limited (429)",
            retry_after=retry_after,
        )

    # 4xx errors (except 429) are not retriable - return None
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


async def fetch_user_data(user_id: str) -> ClerkUserData | None:
    """Fetch full user data from Clerk API.

    This is used when the user doesn't have complete profile data stored.
    Returns avatar_url (which comes from GitHub if using GitHub OAuth),
    name, email, and github_username.

    RETRY: 3 attempts with exponential backoff (0.5s, 1s, 2s) for transient failures.
    CIRCUIT BREAKER: Opens after 5 consecutive failures, recovers after 60 seconds.
    BACKOFF: 300s per-user backoff only after all retries exhausted.
    """
    settings = get_settings()
    if not settings.clerk_secret_key:
        return None

    # Check backoff (only set after retries exhausted)
    if _is_in_backoff(user_id):
        logger.debug(f"User {user_id} in backoff period, skipping Clerk API call")
        return None

    try:
        return await _fetch_user_data_with_retry(user_id)
    except RETRIABLE_EXCEPTIONS as e:
        # All retries exhausted - set backoff for this user
        _set_backoff(user_id)
        logger.warning(f"All retries exhausted fetching user {user_id} from Clerk: {e}")
        return None
    except Exception as e:
        # Bug in our code - don't backoff, let it surface in logs
        logger.exception(f"Unexpected error fetching user data from Clerk: {e}")
        return None


async def fetch_github_username(user_id: str) -> str | None:
    """Fetch GitHub username directly from Clerk API.

    This is used when the user doesn't have a github_username stored.
    """
    clerk_data = await fetch_user_data(user_id)
    return clerk_data.github_username if clerk_data else None
