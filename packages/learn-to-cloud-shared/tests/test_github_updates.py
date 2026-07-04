"""Unit tests for the curriculum GitHub commit helper (/stats panel)."""

from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from learn_to_cloud_shared import github_updates

pytestmark = pytest.mark.unit


@pytest.fixture(autouse=True)
def _clear_cache():
    github_updates._CACHE.clear()
    yield
    github_updates._CACHE.clear()


def _commit_payload() -> list[dict]:
    return [
        {
            "html_url": "https://github.com/learntocloud/x/commit/abc",
            "author": {"login": "octocat"},
            "commit": {
                "message": "Fix things\n\nlonger body",
                "author": {"name": "Octo Cat", "date": "2026-01-02T03:04:05Z"},
                "committer": {"date": "2026-01-02T03:04:05Z"},
            },
        }
    ]


def _mock_response(payload: list[dict]) -> MagicMock:
    response = MagicMock()
    response.json.return_value = payload
    return response


async def test_parses_latest_commit_per_repo():
    with patch.object(
        github_updates,
        "github_api_get",
        new=AsyncMock(return_value=_mock_response(_commit_payload())),
    ):
        updates = await github_updates.get_latest_curriculum_commits()

    assert len(updates) == len(github_updates.CURRICULUM_REPOS)
    first = updates[0]
    assert first.available is True
    assert first.commit_message == "Fix things"  # first line only
    assert first.commit_author == "octocat"
    assert first.commit_url == "https://github.com/learntocloud/x/commit/abc"
    assert first.committed_at is not None


async def test_degrades_gracefully_on_http_error():
    with patch.object(
        github_updates,
        "github_api_get",
        new=AsyncMock(side_effect=httpx.ConnectError("boom")),
    ):
        updates = await github_updates.get_latest_curriculum_commits()

    assert len(updates) == len(github_updates.CURRICULUM_REPOS)
    assert all(u.available is False for u in updates)
    assert all(u.commit_message is None for u in updates)


async def test_empty_commit_list_is_unavailable():
    with patch.object(
        github_updates,
        "github_api_get",
        new=AsyncMock(return_value=_mock_response([])),
    ):
        updates = await github_updates.get_latest_curriculum_commits()

    assert all(u.available is False for u in updates)


async def test_successful_lookups_are_cached():
    mock_get = AsyncMock(return_value=_mock_response(_commit_payload()))
    with patch.object(github_updates, "github_api_get", new=mock_get):
        await github_updates.get_latest_curriculum_commits()
        first_call_count = mock_get.await_count
        await github_updates.get_latest_curriculum_commits()

    # Second call served entirely from cache — no further HTTP calls.
    assert mock_get.await_count == first_call_count
