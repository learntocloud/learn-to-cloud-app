"""Complete, attempt-scoped pagination of GitHub job results."""

from unittest.mock import AsyncMock, call

import httpx2
import pytest
from pydantic import ValidationError

from learn_to_cloud.verification import github_api
from learn_to_cloud.verification.github_api import (
    GitHubClient,
    WorkflowJobsResponseError,
)


def _job(identifier, **updates):
    return {
        "id": identifier,
        "run_id": 789,
        "run_attempt": 2,
        "head_sha": "a" * 40,
        "name": "test",
        "status": "completed",
        "conclusion": "success",
        **updates,
    }


def _response(total, jobs):
    return httpx2.Response(200, json={"total_count": total, "jobs": jobs})


async def test_collects_required_jobs_beyond_first_page(monkeypatch):
    get = AsyncMock(
        side_effect=[
            _response(103, [_job(i, name=f"other-{i}") for i in range(1, 101)]),
            _response(
                103,
                [
                    _job(i, name=name)
                    for i, name in enumerate(("test", "build", "deploy"), 101)
                ],
            ),
        ]
    )
    monkeypatch.setattr(github_api, "github_api_get", get)
    result = await GitHubClient().jobs_for_attempt("o", "r", 789, 2)
    assert len(result) == 103
    assert [job.name for job in result[-3:]] == ["test", "build", "deploy"]
    url = "https://api.github.com/repos/o/r/actions/runs/789/attempts/2/jobs"
    assert get.await_args_list == [
        call(url, params={"per_page": 100, "page": 1}),
        call(url, params={"per_page": 100, "page": 2}),
    ]


@pytest.mark.parametrize(
    "responses",
    [
        [_response(1, [_job(1), _job(2)])],
        [_response(1, [])],
        [_response(2, [_job(1)]), _response(2, [])],
        [_response(2, [_job(1)]), _response(2, [_job(1)])],
        [_response(2, [_job(1)]), _response(3, [_job(2)])],
        [_response(1, [_job(1, run_id=999)])],
        [_response(1, [_job(1, run_attempt=1)])],
    ],
)
async def test_incomplete_or_inconsistent_listing_is_rejected(monkeypatch, responses):
    monkeypatch.setattr(github_api, "github_api_get", AsyncMock(side_effect=responses))
    with pytest.raises(WorkflowJobsResponseError):
        await GitHubClient().jobs_for_attempt("o", "r", 789, 2)


async def test_pagination_limit_never_returns_partial_success(monkeypatch):
    monkeypatch.setattr(github_api, "_JOBS_MAX_PAGES", 1)
    monkeypatch.setattr(
        github_api,
        "github_api_get",
        AsyncMock(return_value=_response(2, [_job(1)])),
    )
    with pytest.raises(WorkflowJobsResponseError, match="pagination limit"):
        await GitHubClient().jobs_for_attempt("o", "r", 789, 2)


@pytest.mark.parametrize(
    "field", ["id", "run_id", "head_sha", "name", "status", "conclusion"]
)
async def test_required_metadata_cannot_be_omitted(monkeypatch, field):
    job = _job(1)
    del job[field]
    monkeypatch.setattr(
        github_api, "github_api_get", AsyncMock(return_value=_response(1, [job]))
    )
    with pytest.raises(ValidationError):
        await GitHubClient().jobs_for_attempt("o", "r", 789, 2)


async def test_optional_run_attempt_is_not_required(monkeypatch):
    job = _job(1)
    del job["run_attempt"]
    monkeypatch.setattr(
        github_api, "github_api_get", AsyncMock(return_value=_response(1, [job]))
    )
    result = await GitHubClient().jobs_for_attempt("o", "r", 789, 2)
    assert len(result) == 1 and result[0].run_attempt is None
