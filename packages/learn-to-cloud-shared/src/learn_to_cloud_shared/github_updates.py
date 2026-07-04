"""Latest-commit lookups for the curriculum repos (powers /stats).

Reuses the resilient ``github_api_get`` seam (auth headers, retry, and
5xx/429 mapping) rather than hand-rolling httpx. Results are cached in a
short-lived process-level ``TTLCache`` because the /stats page is public
and the unauthenticated GitHub API is rate limited (60 req/hr/IP). Any
lookup failure degrades to an ``unavailable`` entry so the page still
renders.
"""

from __future__ import annotations

import logging
from datetime import datetime

import httpx
from cachetools import TTLCache

from learn_to_cloud_shared.schemas import RepoUpdate
from learn_to_cloud_shared.verification.github_http import github_api_get

logger = logging.getLogger(__name__)

# Curriculum repos surfaced on /stats, in display order.
CURRICULUM_REPOS: tuple[tuple[str, str], ...] = (
    ("learntocloud", "learn-to-cloud-app"),
    ("learntocloud", "linux-ctfs"),
    ("learntocloud", "networking-lab"),
)

# One shared entry keyed by "owner/repo"; ~10 min is fresh enough for a
# "latest curriculum updates" panel and keeps us well under the rate limit.
_CACHE: TTLCache[str, RepoUpdate] = TTLCache(maxsize=32, ttl=600)


def _parse_commit(owner: str, repo: str, payload: dict) -> RepoUpdate:
    """Build a RepoUpdate from a GitHub commit JSON object."""
    commit = payload.get("commit") or {}
    author = commit.get("author") or {}
    committer = commit.get("committer") or {}
    login = (payload.get("author") or {}).get("login")

    committed_at: datetime | None = None
    raw_date = committer.get("date") or author.get("date")
    if raw_date:
        try:
            committed_at = datetime.fromisoformat(raw_date.replace("Z", "+00:00"))
        except ValueError:
            committed_at = None

    message = commit.get("message") or ""
    first_line = message.splitlines()[0] if message else None

    return RepoUpdate(
        name=repo,
        url=f"https://github.com/{owner}/{repo}",
        available=True,
        commit_message=first_line,
        commit_author=login or author.get("name"),
        commit_url=payload.get("html_url"),
        committed_at=committed_at,
    )


def _unavailable(owner: str, repo: str) -> RepoUpdate:
    """Fallback entry when the GitHub lookup fails."""
    return RepoUpdate(
        name=repo,
        url=f"https://github.com/{owner}/{repo}",
        available=False,
    )


async def _fetch_latest_commit(owner: str, repo: str) -> RepoUpdate:
    """Fetch the latest commit for one repo, degrading on any failure."""
    url = f"https://api.github.com/repos/{owner}/{repo}/commits"
    try:
        response = await github_api_get(url, params={"per_page": 1})
        commits = response.json()
        if not commits:
            return _unavailable(owner, repo)
        return _parse_commit(owner, repo, commits[0])
    except (httpx.HTTPError, ValueError, KeyError, IndexError) as exc:
        logger.warning(
            "stats.github_commit_failed",
            extra={"repo": f"{owner}/{repo}", "error": str(exc)},
        )
        return _unavailable(owner, repo)


async def get_latest_curriculum_commits() -> list[RepoUpdate]:
    """Latest commit per curriculum repo, cached for ~10 minutes.

    Never raises: repos whose lookup fails come back as ``unavailable``.
    """
    updates: list[RepoUpdate] = []
    for owner, repo in CURRICULUM_REPOS:
        key = f"{owner}/{repo}"
        cached = _CACHE.get(key)
        if cached is not None:
            updates.append(cached)
            continue
        update = await _fetch_latest_commit(owner, repo)
        # Only cache successful lookups so a transient failure doesn't
        # pin an "unavailable" card for the full TTL.
        if update.available:
            _CACHE[key] = update
        updates.append(update)
    return updates
