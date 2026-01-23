"""Updates service for fetching this week's commits.

Fetches commits from GitHub API for the current week (starting Monday).
Results are cached to avoid hitting GitHub rate limits.

HTTP Client:
- Uses shared httpx.AsyncClient for connection pooling
- Must call close_updates_client() on application shutdown

Cache:
- Uses asyncio.Lock to prevent race conditions on cache access
"""

import asyncio
import os
from datetime import UTC, datetime, timedelta

import httpx
from cachetools import TTLCache

from core import get_logger
from core.config import get_settings

logger = get_logger(__name__)

# Configuration - can be overridden via environment variables
REPO_OWNER = os.getenv("UPDATES_REPO_OWNER", "learntocloud")
REPO_NAME = os.getenv("UPDATES_REPO_NAME", "learn-to-cloud-app")
COMMITS_PER_PAGE = 100

# Cache updates for 5 minutes (300 seconds)
UPDATES_TTL = 300
_updates_cache: TTLCache[str, dict] = TTLCache(maxsize=10, ttl=UPDATES_TTL)
_cache_lock = asyncio.Lock()

# Shared HTTP client for connection pooling
_http_client: httpx.AsyncClient | None = None
_http_client_lock = asyncio.Lock()

# Commit patterns to skip
SKIP_PATTERNS = [
    "[skip ci]",
    "merge branch",
    "merge pull request",
    "update changelog",
]


def _format_week_header(dt: datetime) -> str:
    """Format week header like 'WEEK OF JANUARY 19, 2026'."""
    return f"WEEK OF {dt.strftime('%B %d, %Y').upper()}"


def _should_skip_commit(message: str) -> bool:
    """Check if commit should be filtered out."""
    message_lower = message.lower()
    return any(pattern in message_lower for pattern in SKIP_PATTERNS)


def _categorize_commit(message: str) -> tuple[str, str]:
    """Return emoji and category for a commit based on conventional commit prefix."""
    message_lower = message.lower()

    if message_lower.startswith("feat"):
        return "✨", "feature"
    if message_lower.startswith("fix"):
        return "🐛", "bugfix"
    if message_lower.startswith("docs"):
        return "📚", "docs"
    if message_lower.startswith("test"):
        return "🧪", "test"
    if message_lower.startswith("refactor"):
        return "♻️", "refactor"
    if message_lower.startswith("perf"):
        return "⚡", "performance"
    if message_lower.startswith("chore"):
        return "🔧", "chore"
    if message_lower.startswith("style"):
        return "💄", "style"
    if message_lower.startswith("ci"):
        return "🔄", "ci"
    return "📝", "other"


def _clean_commit_message(message: str) -> str:
    """Clean up commit message for display."""
    # Remove conventional commit prefix
    prefixes = [
        "feat:",
        "fix:",
        "docs:",
        "test:",
        "refactor:",
        "perf:",
        "chore:",
        "style:",
        "ci:",
    ]
    for prefix in prefixes:
        if message.lower().startswith(prefix):
            message = message[len(prefix) :].strip()
            break

    # Handle scope: feat(api): message
    if "): " in message and message.find("(") < message.find("):"):
        message = message.split("): ", 1)[-1]

    # Capitalize first letter
    if message:
        message = message[0].upper() + message[1:]

    return message


async def _get_http_client() -> httpx.AsyncClient:
    """Get or create a reusable HTTP client with connection pooling."""
    global _http_client
    if _http_client is not None and not _http_client.is_closed:
        return _http_client

    async with _http_client_lock:
        if _http_client is not None and not _http_client.is_closed:
            return _http_client

        settings = get_settings()
        _http_client = httpx.AsyncClient(
            timeout=settings.http_timeout,
            limits=httpx.Limits(max_connections=10, max_keepalive_connections=5),
        )
        return _http_client


async def close_updates_client() -> None:
    """Close the HTTP client (called on application shutdown)."""
    global _http_client
    if _http_client is None:
        return
    if not _http_client.is_closed:
        await _http_client.aclose()
    _http_client = None


def _get_current_week_monday() -> datetime:
    """Get Monday 00:00:00 UTC of the current week."""
    now = datetime.now(UTC)
    days_since_monday = now.weekday()
    monday = now - timedelta(days=days_since_monday)
    return monday.replace(hour=0, minute=0, second=0, microsecond=0)


async def get_updates() -> dict:
    """Fetch and return this week's commits.

    Returns cached data if available, otherwise fetches from GitHub API.
    Uses async lock to prevent cache race conditions.

    Returns:
        dict with keys:
        - week_start: ISO date string of Monday
        - week_display: Human readable week header
        - commits: list of commit objects
        - repo: repository info
        - generated_at: timestamp
    """
    cache_key = "updates"

    # Check cache first (with lock for thread safety)
    async with _cache_lock:
        cached = _updates_cache.get(cache_key)
        if cached is not None:
            logger.debug("updates.cache_hit")
            return cached

    logger.info("updates.fetching_from_github")

    # Get this week's Monday
    now = datetime.now(UTC)
    monday = _get_current_week_monday()

    # Build GitHub API request
    github_token = os.getenv("GITHUB_TOKEN")
    headers = {"Accept": "application/vnd.github.v3+json"}
    if github_token:
        headers["Authorization"] = f"token {github_token}"

    url = f"https://api.github.com/repos/{REPO_OWNER}/{REPO_NAME}/commits"
    params = {
        "since": monday.isoformat(),
        "per_page": COMMITS_PER_PAGE,
    }

    try:
        client = await _get_http_client()
        response = await client.get(url, headers=headers, params=params)
        response.raise_for_status()
        commits_data = response.json()
    except httpx.HTTPError as e:
        logger.error("updates.github_fetch_failed", error=str(e))
        return {
            "week_start": monday.strftime("%Y-%m-%d"),
            "week_display": _format_week_header(monday),
            "commits": [],
            "repo": {"owner": REPO_OWNER, "name": REPO_NAME},
            "generated_at": now.isoformat(),
            "error": str(e),
        }

    # Process commits for this week
    commits = []
    for commit in commits_data:
        message = commit["commit"]["message"].split("\n")[0]  # First line only

        if _should_skip_commit(message):
            continue

        commit_date = datetime.fromisoformat(
            commit["commit"]["author"]["date"].replace("Z", "+00:00")
        )

        emoji, category = _categorize_commit(message)
        clean_message = _clean_commit_message(message)

        commits.append(
            {
                "sha": commit["sha"][:7],
                "message": clean_message,
                "author": commit["commit"]["author"]["name"],
                "date": commit_date.strftime("%Y-%m-%d"),
                "url": commit["html_url"],
                "emoji": emoji,
                "category": category,
            }
        )

    result = {
        "week_start": monday.strftime("%Y-%m-%d"),
        "week_display": _format_week_header(monday),
        "commits": commits,
        "repo": {"owner": REPO_OWNER, "name": REPO_NAME},
        "generated_at": now.isoformat(),
    }

    # Cache the result (with lock for thread safety)
    async with _cache_lock:
        _updates_cache[cache_key] = result
    logger.info("updates.cached", commits_count=len(commits))

    return result


async def clear_updates_cache() -> None:
    """Clear the updates cache. Useful for testing."""
    async with _cache_lock:
        _updates_cache.clear()
