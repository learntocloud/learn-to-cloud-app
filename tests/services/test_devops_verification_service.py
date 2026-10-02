"""Phase 5 trusts complete current-commit workflow and job outcomes."""

from unittest.mock import AsyncMock

import httpx
import pytest

from learn_to_cloud.verification.devops_analysis import verify_devops_pipeline
from learn_to_cloud.verification.github_api import (
    GitHub,
    GitHubClient,
    WorkflowJob,
)

SHA = "a" * 40


def _run(**updates):
    return {
        "id": 789,
        "run_number": 12,
        "run_attempt": 2,
        "head_branch": "main",
        "head_sha": SHA,
        "event": "push",
        "status": "completed",
        "conclusion": "success",
        **updates,
    }


def _job(name, identifier, **updates):
    return WorkflowJob.model_validate(
        {
            "id": identifier,
            "run_id": 789,
            "run_attempt": 2,
            "head_sha": SHA,
            "name": name,
            "status": "completed",
            "conclusion": "success",
            **updates,
        }
    )


@pytest.fixture
def ports():
    github = AsyncMock(spec=GitHub)
    github.latest_run.return_value = _run()
    github.jobs_for_attempt.return_value = [
        _job(name, index) for index, name in enumerate(("test", "build", "deploy"), 1)
    ]
    github.head_sha.return_value = SHA
    return github


async def test_success_uses_captured_attempt_and_safe_run_url(ports):
    github = ports
    github.latest_run.return_value = _run(html_url="https://untrusted.example/run")
    result = await verify_devops_pipeline("learner", "journal", github)
    assert result.is_valid and result.verification_completed
    assert "https://github.com/learner/journal/actions/runs/789" in result.message
    assert "untrusted" not in result.message
    assert result.task_results is not None
    assert [task.task_name for task in result.task_results] == [
        "test",
        "build",
        "deploy",
    ]
    github.jobs_for_attempt.assert_awaited_once_with("learner", "journal", 789, 2)
    github.head_sha.assert_awaited_once_with("learner", "journal")


async def test_manual_run_on_current_main_is_allowed(ports):
    github = ports
    github.latest_run.return_value = _run(event="workflow_dispatch")
    assert (await verify_devops_pipeline("o", "r", github)).is_valid


@pytest.mark.parametrize(
    "run",
    [
        None,
        _run(conclusion="failure"),
        _run(conclusion="cancelled"),
        _run(conclusion="skipped"),
        _run(status="in_progress", conclusion=None),
        _run(head_branch="feature"),
    ],
)
async def test_unsuccessful_or_missing_latest_run_does_not_read_jobs(ports, run):
    github = ports
    github.latest_run.return_value = run
    result = await verify_devops_pipeline("o", "r", github)
    assert not result.is_valid and result.verification_completed
    github.jobs_for_attempt.assert_not_awaited()


@pytest.mark.parametrize(
    "updates",
    [
        {"id": "789"},
        {"run_attempt": 0},
        {"head_sha": "short"},
        {"status": "unknown"},
        {"conclusion": None},
    ],
)
async def test_malformed_run_is_incomplete(ports, updates):
    github = ports
    github.latest_run.return_value = _run(**updates)
    result = await verify_devops_pipeline("o", "r", github)
    assert not result.is_valid and not result.verification_completed
    github.jobs_for_attempt.assert_not_awaited()


@pytest.mark.parametrize("missing", ["run_attempt", "id", "head_sha", "conclusion"])
async def test_required_run_metadata_cannot_be_omitted(ports, missing):
    github = ports
    run = _run()
    del run[missing]
    github.latest_run.return_value = run
    result = await verify_devops_pipeline("o", "r", github)
    assert not result.verification_completed


async def test_success_on_old_commit_does_not_pass(ports):
    github = ports
    github.head_sha.return_value = "b" * 40
    result = await verify_devops_pipeline("o", "r", github)
    assert not result.is_valid and result.verification_completed
    assert "current main commit" in result.message


@pytest.mark.parametrize("sha", ["", "bad", None])
async def test_malformed_current_commit_is_incomplete(ports, sha):
    github = ports
    github.head_sha.return_value = sha
    result = await verify_devops_pipeline("o", "r", github)
    assert not result.verification_completed


@pytest.mark.parametrize(
    "outcome", ["failure", "skipped", "cancelled", "neutral", "timed_out"]
)
@pytest.mark.parametrize("name", ["test", "build", "deploy"])
async def test_green_run_cannot_hide_unsuccessful_required_job(ports, name, outcome):
    github = ports
    github.jobs_for_attempt.return_value = [
        job.model_copy(update={"conclusion": outcome}) if job.name == name else job
        for job in github.jobs_for_attempt.return_value
    ]
    result = await verify_devops_pipeline("o", "r", github)
    assert not result.is_valid and result.verification_completed
    assert result.task_results is not None
    failed = [task for task in result.task_results if not task.passed]
    assert [task.task_name for task in failed] == [name]


async def test_unfinished_required_job_cannot_pass(ports):
    github = ports
    github.jobs_for_attempt.return_value[0] = _job(
        "test", 1, status="in_progress", conclusion=None
    )
    result = await verify_devops_pipeline("o", "r", github)
    assert not result.is_valid and result.verification_completed


@pytest.mark.parametrize(
    "names",
    [
        [],
        ["deploy"],
        ["test", "build"],
        ["Test", "build", "deploy"],
        ["test (3.13)", "build", "deploy"],
        ["test", "test", "build", "deploy"],
    ],
)
async def test_missing_or_ambiguous_names_require_full_rerun(ports, names):
    github = ports
    github.jobs_for_attempt.return_value = [
        _job(name, index) for index, name in enumerate(names, 1)
    ]
    result = await verify_devops_pipeline("o", "r", github)
    assert not result.is_valid and result.verification_completed
    assert result.task_results is not None
    assert any("Re-run all jobs" in task.next_steps for task in result.task_results)


@pytest.mark.parametrize(
    "updates",
    [
        {"run_id": 999},
        {"run_attempt": 1},
        {"head_sha": "b" * 40},
        {"conclusion": None},
        {"id": 2},
    ],
)
async def test_inconsistent_job_identity_or_metadata_is_incomplete(ports, updates):
    github = ports
    github.jobs_for_attempt.return_value[0] = _job("test", 1, **updates)
    result = await verify_devops_pipeline("o", "r", github)
    assert not result.is_valid and not result.verification_completed


async def test_additional_jobs_and_optional_attempt_field_are_allowed(ports):
    github = ports
    github.jobs_for_attempt.return_value.append(_job("docs", 4, run_attempt=None))
    result = await verify_devops_pipeline("o", "r", github)
    assert result.is_valid


@pytest.mark.parametrize("stage", ["workflow", "jobs", "branch"])
@pytest.mark.parametrize("status", [401, 403, 404, 429, 500])
async def test_http_failures_are_safe_and_actionable(ports, stage, status):
    github = ports
    error = httpx.HTTPStatusError(
        "sensitive response",
        request=httpx.Request("GET", "https://api.github.com/example"),
        response=httpx.Response(status),
    )
    if stage == "workflow":
        github.latest_run.side_effect = error
    elif stage == "jobs":
        github.jobs_for_attempt.side_effect = error
    else:
        github.head_sha.side_effect = error
    result = await verify_devops_pipeline("o", "r", github)
    assert not result.is_valid
    assert result.verification_completed == (
        status == 404 and stage in ("workflow", "branch")
    )
    assert "sensitive" not in result.model_dump_json()


async def test_network_failure_is_incomplete(ports):
    github = ports
    github.jobs_for_attempt.side_effect = httpx.ConnectError("private details")
    result = await verify_devops_pipeline("o", "r", github)
    assert not result.verification_completed
    assert "private details" not in result.message


async def test_programming_errors_propagate(ports):
    github = ports
    github.jobs_for_attempt.side_effect = RuntimeError("bug")
    with pytest.raises(RuntimeError, match="bug"):
        await verify_devops_pipeline("o", "r", github)


@pytest.mark.parametrize(
    "payload",
    [
        {},
        {"total_count": 1, "jobs": [{}]},
        {"total_count": "0", "jobs": []},
        {"total_count": 1, "jobs": []},
    ],
)
async def test_malformed_jobs_http_payload_is_incomplete(monkeypatch, ports, payload):
    monkeypatch.setattr(
        "learn_to_cloud.verification.github_api.github_api_get",
        AsyncMock(return_value=httpx.Response(200, json=payload)),
    )
    client = GitHubClient()
    client.latest_run = ports.latest_run
    client.head_sha = ports.head_sha
    result = await verify_devops_pipeline("o", "r", client)
    assert not result.is_valid and not result.verification_completed


async def test_latest_workflow_is_requested_without_success_filter(monkeypatch, ports):
    get = AsyncMock(return_value=httpx.Response(200, json={"workflow_runs": [_run()]}))
    monkeypatch.setattr("learn_to_cloud.verification.github_api.github_api_get", get)
    client = GitHubClient()
    client.jobs_for_attempt = ports.jobs_for_attempt
    client.head_sha = ports.head_sha
    result = await verify_devops_pipeline("o", "r", client)
    assert result.is_valid
    get.assert_awaited_once_with(
        "https://api.github.com/repos/o/r/actions/workflows/ci.yml/runs",
        params={"branch": "main", "per_page": 1},
    )
