"""The capstone gate requires a successful manual run on current main."""

from json import JSONDecodeError
from unittest.mock import AsyncMock

import httpx2
import pytest

from learn_to_cloud.verification.ci_status import verify_ci_status
from learn_to_cloud.verification.github_api import GitHub, GitHubClient
from learn_to_cloud.verification.github_errors import GitHubServerError

pytestmark = pytest.mark.unit
SHA = "a" * 40
RUN_URL = "https://github.com/testuser/journal-starter/actions/runs/789"


@pytest.fixture
def github():
    github = AsyncMock(spec=GitHub)
    github.latest_run.return_value = {
        "id": 789,
        "run_number": 10,
        "head_branch": "main",
        "head_sha": SHA,
        "event": "workflow_dispatch",
        "status": "completed",
        "conclusion": "success",
    }
    github.head_sha.return_value = SHA
    return github


async def test_capstone_passes_only_on_current_commit(github):
    result = await verify_ci_status("testuser", "journal-starter", github)

    github.latest_run.assert_awaited_once_with(
        "testuser", "journal-starter", "verify-capstone.yml"
    )
    github.head_sha.assert_awaited_once_with("testuser", "journal-starter")
    assert result.is_valid and result.verification_completed
    assert result.task_results is not None
    assert len(result.task_results) == 1
    assert result.task_results[0].passed
    assert SHA in result.task_results[0].feedback
    assert RUN_URL in result.task_results[0].feedback
    assert not result.task_results[0].criterion_results


async def test_no_runs_requires_manual_dispatch(github):
    github.latest_run.return_value = None
    result = await verify_ci_status("testuser", "journal-starter", github)
    assert not result.is_valid
    assert "No Verify capstone runs" in result.message
    assert "Run workflow" in result.message
    github.head_sha.assert_not_awaited()


@pytest.mark.parametrize(
    "status", ["queued", "in_progress", "waiting", "pending", "requested"]
)
async def test_pending_run_does_not_accept_earlier_success(github, status):
    github.latest_run.return_value.update(status=status, conclusion=None)
    result = await verify_ci_status("testuser", "journal-starter", github)
    assert not result.is_valid
    assert status in result.message
    assert RUN_URL in result.message
    assert github.latest_run.await_count == 1
    github.head_sha.assert_not_awaited()


@pytest.mark.parametrize(
    "conclusion",
    ["failure", "cancelled", "skipped", "timed_out", "action_required", "neutral"],
)
async def test_unsuccessful_run_does_not_accept_earlier_success(github, conclusion):
    github.latest_run.return_value["conclusion"] = conclusion
    result = await verify_ci_status("testuser", "journal-starter", github)
    assert not result.is_valid
    assert conclusion in result.message
    assert RUN_URL in result.message
    assert "Run workflow" in result.message
    assert github.latest_run.await_count == 1
    github.head_sha.assert_not_awaited()


async def test_success_on_old_commit_requires_rerun(github):
    github.head_sha.return_value = "b" * 40
    result = await verify_ci_status("testuser", "journal-starter", github)
    assert not result.is_valid
    assert "Rerun Verify capstone" in result.message
    assert result.task_results is None


@pytest.mark.parametrize(
    ("field", "value"), [("head_branch", "feature"), ("event", "push")]
)
async def test_wrong_invocation_does_not_pass(github, field, value):
    github.latest_run.return_value[field] = value
    result = await verify_ci_status("testuser", "journal-starter", github)
    assert not result.is_valid
    assert "manually on main" in result.message
    github.head_sha.assert_not_awaited()


@pytest.mark.parametrize(
    "field",
    ["id", "run_number", "head_branch", "event", "head_sha", "status", "conclusion"],
)
async def test_missing_metadata_is_unavailable(github, caplog, field):
    del github.latest_run.return_value[field]
    result = await verify_ci_status("testuser", "journal-starter", github)
    assert not result.is_valid and not result.verification_completed
    assert "capstone.invalid_metadata" in caplog.text


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("id", True),
        ("id", 0),
        ("head_sha", "private-invalid-sha"),
        ("status", "unknown"),
        ("conclusion", None),
    ],
)
async def test_invalid_metadata_is_unavailable(github, caplog, field, value):
    github.latest_run.return_value[field] = value
    result = await verify_ci_status("testuser", "journal-starter", github)
    assert not result.is_valid and not result.verification_completed
    assert "private-invalid-sha" not in caplog.text + result.message


@pytest.mark.parametrize("sha", [None, "", "not-a-sha"])
async def test_missing_or_invalid_main_sha_is_unavailable(github, sha):
    github.head_sha.return_value = sha
    result = await verify_ci_status("testuser", "journal-starter", github)
    assert not result.is_valid and not result.verification_completed


def _http_error(status):
    response = httpx2.Response(status, request=httpx2.Request("GET", "https://test"))
    return httpx2.HTTPStatusError(
        "private response", request=response.request, response=response
    )


@pytest.mark.parametrize("source", ["workflow", "branch"])
async def test_missing_resource_explains_required_action(github, source):
    lookup = github.latest_run if source == "workflow" else github.head_sha
    lookup.side_effect = _http_error(404)
    result = await verify_ci_status("testuser", "journal-starter", github)
    assert not result.is_valid and result.verification_completed
    if source == "workflow":
        assert "verify-capstone.yml" in result.message
        assert "Sync your fork" in result.message
        assert "enable GitHub Actions" in result.message
    else:
        assert "main branch" in result.message


@pytest.mark.parametrize("source", ["workflow", "branch"])
@pytest.mark.parametrize(
    "error",
    [
        _http_error(401),
        _http_error(403),
        GitHubServerError("private response", status_code=429),
        GitHubServerError("private response", status_code=503),
        httpx2.ConnectError("private response"),
        httpx2.ReadTimeout("private response"),
        JSONDecodeError("private response", "", 0),
    ],
)
async def test_provider_errors_are_unavailable(github, source, error):
    lookup = github.latest_run if source == "workflow" else github.head_sha
    lookup.side_effect = error
    result = await verify_ci_status("testuser", "journal-starter", github)
    assert not result.is_valid and not result.verification_completed
    assert "private response" not in result.message


@pytest.mark.parametrize("source", ["workflow", "branch"])
async def test_programming_errors_propagate(github, source):
    lookup = github.latest_run if source == "workflow" else github.head_sha
    lookup.side_effect = RuntimeError("bug")
    with pytest.raises(RuntimeError, match="bug"):
        await verify_ci_status("testuser", "journal-starter", github)


@pytest.mark.parametrize("payload", [[], None, {}, {"workflow_runs": [None]}])
async def test_malformed_workflow_response_is_unavailable(monkeypatch, github, payload):
    monkeypatch.setattr(
        "learn_to_cloud.verification.github_api.github_api_get",
        AsyncMock(return_value=httpx2.Response(200, json=payload)),
    )
    client = GitHubClient()
    client.head_sha = github.head_sha
    result = await verify_ci_status("testuser", "journal-starter", client)
    assert not result.is_valid and not result.verification_completed


async def test_malformed_branch_response_is_unavailable(monkeypatch, github):
    monkeypatch.setattr(
        "learn_to_cloud.verification.github_api.github_api_get",
        AsyncMock(return_value=httpx2.Response(200, json=[])),
    )
    client = GitHubClient()
    client.latest_run = github.latest_run
    result = await verify_ci_status("testuser", "journal-starter", client)
    assert not result.is_valid and not result.verification_completed
