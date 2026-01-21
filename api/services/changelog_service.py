"""Changelog service for fetching and caching commit history.

Fetches commits from GitHub API and groups them by week for display
in the changelog page. Results are cached to avoid hitting GitHub rate limits.

HTTP Client:
- Uses shared httpx.AsyncClient for connection pooling
- Must call close_changelog_client() on application shutdown

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
REPO_OWNER = os.getenv("CHANGELOG_REPO_OWNER", "learntocloud")
REPO_NAME = os.getenv("CHANGELOG_REPO_NAME", "learn-to-cloud-app")
WEEKS_TO_FETCH = 8
COMMITS_PER_PAGE = 100

# Cache changelog for 5 minutes (300 seconds)
# This is longer than other caches since commits don't change that often
CHANGELOG_TTL = 300
_changelog_cache: TTLCache[str, dict] = TTLCache(maxsize=10, ttl=CHANGELOG_TTL)
_cache_lock = asyncio.Lock()

# Shared HTTP client for connection pooling
_http_client: httpx.AsyncClient | None = None
_http_client_lock = asyncio.Lock()

# Easter eggs for week headers
EASTER_EGGS = [
    "ship it! 🚀",
    "another week, another feature ✨",
    "bugs squashed 🐛",
    "coffee consumed: ∞ ☕",
    "powered by late nights 🌙",
    "learning in progress... 📚",
    "cloud all the things ☁️",
    "terraform apply -auto-approve 😅",
]

# Commit patterns to skip
SKIP_PATTERNS = [
    "[skip ci]",
    "merge branch",
    "merge pull request",
    "update changelog",
]


def _get_week_start(dt: datetime) -> datetime:
    """Get the Monday of the week for the given datetime."""
    days_since_monday = dt.weekday()
    return dt - timedelta(days=days_since_monday)


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


async def close_changelog_client() -> None:
    """Close the HTTP client (called on application shutdown)."""
    global _http_client
    if _http_client is None:
        return
    if not _http_client.is_closed:
        await _http_client.aclose()
    _http_client = None


async def get_changelog() -> dict:
    """Fetch and return changelog data grouped by week.

    Returns cached data if available, otherwise fetches from GitHub API.
    Uses async lock to prevent cache race conditions.

    Returns:
        dict with keys:
        - weeks: list of week objects with commits
        - repo: repository info
        - generated_at: timestamp
    """
    cache_key = "changelog"

    # Check cache first (with lock for thread safety)
    async with _cache_lock:
        cached = _changelog_cache.get(cache_key)
        if cached is not None:
            logger.debug("changelog.cache_hit")
            return cached

    logger.info("changelog.fetching_from_github")

    # Calculate date range
    now = datetime.now(UTC)
    since = now - timedelta(weeks=WEEKS_TO_FETCH)

    # Build GitHub API request
    github_token = os.getenv("GITHUB_TOKEN")
    headers = {"Accept": "application/vnd.github.v3+json"}
    if github_token:
        headers["Authorization"] = f"token {github_token}"

    url = f"https://api.github.com/repos/{REPO_OWNER}/{REPO_NAME}/commits"
    params = {
        "since": since.isoformat(),
        "per_page": COMMITS_PER_PAGE,
    }

    try:
        client = await _get_http_client()
        response = await client.get(url, headers=headers, params=params)
        response.raise_for_status()
        commits_data = response.json()
    except httpx.HTTPError as e:
        logger.error("changelog.github_fetch_failed", error=str(e))
        return {
            "weeks": [],
            "repo": {"owner": REPO_OWNER, "name": REPO_NAME},
            "generated_at": now.isoformat(),
            "error": str(e),
        }

    # Group commits by week
    weeks_map: dict[str, list[dict]] = {}

    for commit in commits_data:
        message = commit["commit"]["message"].split("\n")[0]  # First line only

        if _should_skip_commit(message):
            continue

        commit_date = datetime.fromisoformat(
            commit["commit"]["author"]["date"].replace("Z", "+00:00")
        )
        week_start = _get_week_start(commit_date)
        week_key = week_start.strftime("%Y-%m-%d")

        if week_key not in weeks_map:
            weeks_map[week_key] = []

        emoji, category = _categorize_commit(message)
        clean_message = _clean_commit_message(message)

        weeks_map[week_key].append(
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

    # Convert to sorted list of weeks
    sorted_weeks = sorted(weeks_map.keys(), reverse=True)
    weeks = []
    for i, week_key in enumerate(sorted_weeks):
        week_start = datetime.strptime(week_key, "%Y-%m-%d")
        weeks.append(
            {
                "week_start": week_key,
                "week_display": _format_week_header(week_start),
                "easter_egg": EASTER_EGGS[i % len(EASTER_EGGS)],
                "commits": weeks_map[week_key],
            }
        )

    result = {
        "weeks": weeks,
        "repo": {"owner": REPO_OWNER, "name": REPO_NAME},
        "generated_at": now.isoformat(),
    }

    # Cache the result (with lock for thread safety)
    async with _cache_lock:
        _changelog_cache[cache_key] = result
    logger.info("changelog.cached", weeks_count=len(weeks))

    return result


def clear_changelog_cache() -> None:
    """Clear the changelog cache. Useful for testing."""
    _changelog_cache.clear()
