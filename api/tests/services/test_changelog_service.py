"""Tests for changelog/updates service."""

import asyncio
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from services.changelog_service import (
    SKIP_PATTERNS,
    _categorize_commit,
    _clean_commit_message,
    _format_week_header,
    _get_current_week_monday,
    _get_http_client,
    _should_skip_commit,
    clear_updates_cache,
    close_updates_client,
    get_updates,
)

pytestmark = pytest.mark.unit


class TestFormatWeekHeader:
    """Tests for _format_week_header function."""

    def test_formats_date_correctly(self):
        """Test formats date as 'WEEK OF MONTH DD, YYYY'."""
        dt = datetime(2026, 1, 19, 12, 0, 0, tzinfo=UTC)
        result = _format_week_header(dt)
        assert result == "WEEK OF JANUARY 19, 2026"

    def test_handles_different_months(self):
        """Test works for various months."""
        dt = datetime(2025, 12, 25, tzinfo=UTC)
        result = _format_week_header(dt)
        assert result == "WEEK OF DECEMBER 25, 2025"


class TestShouldSkipCommit:
    """Tests for _should_skip_commit function."""

    @pytest.mark.parametrize(
        "message",
        [
            "[skip ci] update deps",
            "Merge branch 'main' into feature",
            "Merge pull request #123",
            "Update changelog",
        ],
    )
    def test_skips_matching_patterns(self, message: str):
        """Test skips commits matching skip patterns."""
        assert _should_skip_commit(message) is True

    @pytest.mark.parametrize(
        "message",
        [
            "feat: add new feature",
            "fix: resolve bug",
            "docs: update readme",
            "chore: update dependencies",
        ],
    )
    def test_does_not_skip_regular_commits(self, message: str):
        """Test does not skip normal commits."""
        assert _should_skip_commit(message) is False

    def test_case_insensitive(self):
        """Test matching is case-insensitive."""
        assert _should_skip_commit("MERGE BRANCH 'main'") is True
        assert _should_skip_commit("[SKIP CI] test") is True


class TestCategorizeCommit:
    """Tests for _categorize_commit function."""

    @pytest.mark.parametrize(
        "message,expected_emoji,expected_category",
        [
            ("feat: add feature", "✨", "feature"),
            ("fix: resolve issue", "🐛", "bugfix"),
            ("docs: update readme", "📚", "docs"),
            ("test: add unit tests", "🧪", "test"),
            ("refactor: clean up code", "♻️", "refactor"),
            ("perf: optimize query", "⚡", "performance"),
            ("chore: update deps", "🔧", "chore"),
            ("style: format code", "💄", "style"),
            ("ci: update workflow", "🔄", "ci"),
            ("random commit message", "📝", "other"),
        ],
    )
    def test_categorizes_conventional_commits(
        self, message: str, expected_emoji: str, expected_category: str
    ):
        """Test categorizes conventional commit prefixes correctly."""
        emoji, category = _categorize_commit(message)
        assert emoji == expected_emoji
        assert category == expected_category

    def test_case_insensitive(self):
        """Test matching is case-insensitive."""
        emoji, category = _categorize_commit("FEAT: uppercase feature")
        assert category == "feature"


class TestCleanCommitMessage:
    """Tests for _clean_commit_message function."""

    def test_removes_conventional_prefix(self):
        """Test removes conventional commit prefix."""
        result = _clean_commit_message("feat: add new feature")
        assert result == "Add new feature"

    def test_removes_scoped_prefix(self):
        """Test removes prefix with scope."""
        result = _clean_commit_message("feat(api): add new endpoint")
        assert result == "Add new endpoint"

    def test_capitalizes_first_letter(self):
        """Test capitalizes first letter of message."""
        result = _clean_commit_message("fix: lowercase message")
        assert result == "Lowercase message"

    def test_handles_message_without_prefix(self):
        """Test handles message without conventional prefix."""
        result = _clean_commit_message("just a regular message")
        assert result == "Just a regular message"

    def test_handles_empty_message(self):
        """Test handles empty message."""
        result = _clean_commit_message("")
        assert result == ""


class TestGetCurrentWeekMonday:
    """Tests for _get_current_week_monday function."""

    def test_returns_monday_at_midnight_utc(self):
        """Test returns Monday 00:00:00 UTC."""
        monday = _get_current_week_monday()

        assert monday.weekday() == 0  # Monday
        assert monday.hour == 0
        assert monday.minute == 0
        assert monday.second == 0
        assert monday.microsecond == 0
        assert monday.tzinfo == UTC

    def test_returns_current_week_monday(self):
        """Test returns Monday of the current week."""
        now = datetime.now(UTC)
        monday = _get_current_week_monday()

        # Monday should be within the last 7 days
        assert (now - monday).days < 7
        assert monday <= now


class TestGetHttpClient:
    """Tests for _get_http_client function."""

    @pytest.mark.asyncio
    async def test_creates_client_if_none(self):
        """Test creates client when none exists."""
        # Reset module state
        import services.changelog_service as svc

        if svc._http_client is not None and not svc._http_client.is_closed:
            await svc._http_client.aclose()
        svc._http_client = None

        client = await _get_http_client()

        assert client is not None
        assert isinstance(client, httpx.AsyncClient)
        assert not client.is_closed

        # Cleanup
        await client.aclose()
        svc._http_client = None

    @pytest.mark.asyncio
    async def test_reuses_existing_client(self):
        """Test reuses existing open client."""
        import services.changelog_service as svc

        # Create initial client
        if svc._http_client is not None and not svc._http_client.is_closed:
            await svc._http_client.aclose()
        svc._http_client = None

        client1 = await _get_http_client()
        client2 = await _get_http_client()

        assert client1 is client2

        # Cleanup
        await client1.aclose()
        svc._http_client = None


class TestCloseUpdatesClient:
    """Tests for close_updates_client function."""

    @pytest.mark.asyncio
    async def test_closes_open_client(self):
        """Test closes the HTTP client."""
        import services.changelog_service as svc

        # Ensure we have a client
        svc._http_client = None
        client = await _get_http_client()
        assert not client.is_closed

        await close_updates_client()

        assert svc._http_client is None

    @pytest.mark.asyncio
    async def test_handles_no_client(self):
        """Test handles case when no client exists."""
        import services.changelog_service as svc

        svc._http_client = None

        # Should not raise
        await close_updates_client()

        assert svc._http_client is None


class TestGetUpdates:
    """Tests for get_updates function."""

    @pytest.mark.asyncio
    async def test_returns_cached_result(self):
        """Test returns cached result if available."""
        import services.changelog_service as svc

        # Clear and set cache
        await clear_updates_cache()

        cached_data = {
            "week_start": "2026-01-19",
            "week_display": "WEEK OF JANUARY 19, 2026",
            "commits": [{"sha": "abc1234", "message": "Test commit"}],
            "repo": {"owner": "test", "name": "repo"},
            "generated_at": "2026-01-24T12:00:00",
        }

        async with svc._cache_lock:
            svc._updates_cache["updates"] = cached_data

        result = await get_updates()

        assert result == cached_data

        # Cleanup
        await clear_updates_cache()

    @pytest.mark.asyncio
    async def test_fetches_from_github_on_cache_miss(self):
        """Test fetches from GitHub when cache is empty."""
        await clear_updates_cache()

        mock_commits = [
            {
                "sha": "abc1234567890",
                "commit": {
                    "message": "feat: add new feature",
                    "author": {"name": "Test Author", "date": "2026-01-24T10:00:00Z"},
                },
                "html_url": "https://github.com/test/repo/commit/abc1234",
            }
        ]

        with patch("services.changelog_service._get_http_client") as mock_get_client:
            mock_client = AsyncMock()
            mock_response = MagicMock()
            mock_response.raise_for_status = MagicMock()
            mock_response.json.return_value = mock_commits
            mock_client.get = AsyncMock(return_value=mock_response)
            mock_get_client.return_value = mock_client

            result = await get_updates()

            assert "commits" in result
            assert len(result["commits"]) == 1
            assert result["commits"][0]["message"] == "Add new feature"
            assert result["commits"][0]["category"] == "feature"

        await clear_updates_cache()

    @pytest.mark.asyncio
    async def test_handles_github_api_error(self):
        """Test handles GitHub API errors gracefully."""
        await clear_updates_cache()

        with patch("services.changelog_service._get_http_client") as mock_get_client:
            mock_client = AsyncMock()
            mock_client.get = AsyncMock(
                side_effect=httpx.HTTPError("API rate limit exceeded")
            )
            mock_get_client.return_value = mock_client

            result = await get_updates()

            assert "error" in result
            assert result["commits"] == []

        await clear_updates_cache()

    @pytest.mark.asyncio
    async def test_filters_skip_commits(self):
        """Test filters out commits matching skip patterns."""
        await clear_updates_cache()

        mock_commits = [
            {
                "sha": "abc1234567890",
                "commit": {
                    "message": "feat: keep this commit",
                    "author": {"name": "Author", "date": "2026-01-24T10:00:00Z"},
                },
                "html_url": "https://github.com/test/repo/commit/abc1234",
            },
            {
                "sha": "def5678901234",
                "commit": {
                    "message": "Merge pull request #123",
                    "author": {"name": "Author", "date": "2026-01-24T11:00:00Z"},
                },
                "html_url": "https://github.com/test/repo/commit/def5678",
            },
        ]

        with patch("services.changelog_service._get_http_client") as mock_get_client:
            mock_client = AsyncMock()
            mock_response = MagicMock()
            mock_response.raise_for_status = MagicMock()
            mock_response.json.return_value = mock_commits
            mock_client.get = AsyncMock(return_value=mock_response)
            mock_get_client.return_value = mock_client

            result = await get_updates()

            assert len(result["commits"]) == 1
            assert result["commits"][0]["message"] == "Keep this commit"

        await clear_updates_cache()


class TestClearUpdatesCache:
    """Tests for clear_updates_cache function."""

    @pytest.mark.asyncio
    async def test_clears_cache(self):
        """Test clears the updates cache."""
        import services.changelog_service as svc

        # Add something to cache
        async with svc._cache_lock:
            svc._updates_cache["updates"] = {"test": "data"}

        await clear_updates_cache()

        async with svc._cache_lock:
            assert "updates" not in svc._updates_cache
