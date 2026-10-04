"""Phase 6 finds the learner's production URL from GitHub and probes it."""

from unittest.mock import AsyncMock

import httpx2
import pytest

from learn_to_cloud.schemas.verification import ValidationResult
from learn_to_cloud.verification import secure_deployment
from learn_to_cloud.verification.github_api import Deployment, DeploymentStatus
from tests.support.fakes.github import FakeGitHub

_SHA = "a" * 40
_URL = "https://journal.example"
_PASS = ValidationResult(is_valid=True, message="ok")


def _github(
    *,
    sha: str | None = _SHA,
    deployment: bool = True,
    state: str = "success",
    url: str = _URL,
    **kwargs,
) -> FakeGitHub:
    return FakeGitHub(
        sha=sha,
        deployment=Deployment(
            id=7, sha=_SHA, environment="production", performed_via_github_app=None
        )
        if deployment
        else None,
        deployment_status=DeploymentStatus(
            state=state, environment_url=url, log_url=""
        ),
        **kwargs,
    )


@pytest.fixture
def probes(monkeypatch):
    plaintext = AsyncMock(return_value=_PASS)
    hsts = AsyncMock(return_value=_PASS)
    monkeypatch.setattr(secure_deployment, "verify_plaintext_http_blocked", plaintext)
    monkeypatch.setattr(secure_deployment, "verify_hsts", hsts)
    return plaintext, hsts


async def test_probes_the_production_url_of_the_current_main_commit(probes):
    github = _github()
    github.latest_deployment = AsyncMock(wraps=github.latest_deployment)

    result = await secure_deployment.verify_secure_deployment("me", "repo", github)

    assert result.is_valid
    github.latest_deployment.assert_awaited_once_with("me", "repo", _SHA, "production")
    for probe in probes:
        probe.assert_awaited_once_with(_URL)
    assert [(t.task_name, t.passed) for t in result.task_results or []] == [
        ("https-only", True),
        ("hsts", True),
    ]


@pytest.mark.parametrize(
    ("github", "text"),
    [
        (_github(sha=None), "latest commit"),
        (_github(deployment=False), "No production deployment"),
        (_github(state="failure"), "is failure"),
        (_github(url=""), "has no URL"),
    ],
)
async def test_missing_production_deployment_fails_without_probing(
    probes, github, text
):
    result = await secure_deployment.verify_secure_deployment("me", "repo", github)

    assert not result.is_valid and result.verification_completed
    assert text in result.message
    assert "production" in result.message
    for probe in probes:
        probe.assert_not_awaited()


async def test_github_outage_is_not_counted_against_the_learner(probes):
    response = httpx2.Response(503, request=httpx2.Request("GET", "https://api"))
    error = httpx2.HTTPStatusError("down", request=response.request, response=response)

    result = await secure_deployment.verify_secure_deployment(
        "me", "repo", _github(sha_error=error)
    )

    assert not result.is_valid and not result.verification_completed
    for probe in probes:
        probe.assert_not_awaited()


@pytest.mark.parametrize(
    ("plaintext", "hsts", "failed"),
    [
        (False, True, ["https-only"]),
        (True, False, ["hsts"]),
        (False, False, ["https-only", "hsts"]),
    ],
)
async def test_any_failed_probe_fails_with_per_check_feedback(
    probes, plaintext, hsts, failed
):
    for probe, passed in zip(probes, (plaintext, hsts), strict=True):
        probe.return_value = ValidationResult(is_valid=passed, message="detail")

    result = await secure_deployment.verify_secure_deployment("me", "repo", _github())

    assert not result.is_valid and result.verification_completed
    tasks = result.task_results or []
    assert [t.task_name for t in tasks if not t.passed] == failed
    assert all(t.next_steps for t in tasks if not t.passed)


async def test_unreachable_probe_marks_the_attempt_incomplete(probes):
    probes[1].return_value = ValidationResult(
        is_valid=False, verification_completed=False, message="unavailable"
    )

    result = await secure_deployment.verify_secure_deployment("me", "repo", _github())

    assert not result.is_valid and not result.verification_completed
