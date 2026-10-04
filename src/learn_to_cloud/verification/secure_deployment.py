"""Phase 6 live-API hardening: plain HTTP is not served and HSTS is sent.

The API URL comes from the GitHub ``production`` deployment that Phase 5's
deploy job records for the current ``main`` commit, so learners submit nothing
and can only point verification at their own deployment.
"""

from __future__ import annotations

from json import JSONDecodeError

import httpx2
from opentelemetry import trace
from pydantic import ValidationError

from learn_to_cloud.schemas.verification import TaskResult, ValidationResult
from learn_to_cloud.verification.deployed_api import (
    verify_hsts,
    verify_plaintext_http_blocked,
)
from learn_to_cloud.verification.devops_verification import DEVOPS_ENVIRONMENT
from learn_to_cloud.verification.github_api import GitHub
from learn_to_cloud.verification.github_errors import github_error_to_result
from learn_to_cloud.verification.github_http import RETRIABLE_EXCEPTIONS

_DEPLOY_INSTRUCTIONS = (
    "Phase 6 checks the live API your Phase 5 deploy job records as the "
    "`production` environment. Push to main, let the deploy job finish, and "
    "keep the API running until verification passes."
)


def _not_found(message: str) -> ValidationResult:
    return ValidationResult(is_valid=False, message=f"{message} {_DEPLOY_INSTRUCTIONS}")


async def _production_url(
    owner: str, repo: str, github: GitHub
) -> str | ValidationResult:
    head_sha = await github.head_sha(owner, repo)
    if not head_sha:
        return _not_found("Could not read the latest commit on your main branch.")
    deployment = await github.latest_deployment(
        owner, repo, head_sha, DEVOPS_ENVIRONMENT
    )
    if deployment is None:
        return _not_found(
            "No production deployment was recorded for your latest main commit."
        )
    status = await github.latest_deployment_status(owner, repo, deployment.id)
    if status is None or status.state != "success":
        state = status.state if status else "missing a status"
        return _not_found(f"The latest production deployment is {state}.")
    if not status.environment_url:
        return _not_found(
            "The production deployment has no URL. Set `url:` on the deploy "
            "job's environment."
        )
    return status.environment_url


async def verify_secure_deployment(
    owner: str, repo: str, github: GitHub
) -> ValidationResult:
    """Require the production API to refuse plain HTTP and send HSTS."""
    try:
        url = await _production_url(owner, repo, github)
    except (ValidationError, JSONDecodeError, UnicodeDecodeError):
        trace.get_current_span().add_event("secure_deployment.invalid_metadata")
        return ValidationResult(
            is_valid=False,
            verification_completed=False,
            message="Couldn't read your GitHub deployment records. Try again later.",
        )
    except (httpx2.HTTPStatusError, *RETRIABLE_EXCEPTIONS) as exc:
        return github_error_to_result(exc, event="secure_deployment.api_error")
    if isinstance(url, ValidationResult):
        return url

    plaintext = await verify_plaintext_http_blocked(url)
    hsts = await verify_hsts(url)
    task_results = [
        TaskResult(
            task_name="https-only",
            passed=plaintext.is_valid,
            feedback=plaintext.message,
            next_steps=""
            if plaintext.is_valid
            else "Redirect HTTP to HTTPS (or close port 80), then verify again.",
        ),
        TaskResult(
            task_name="hsts",
            passed=hsts.is_valid,
            feedback=hsts.message,
            next_steps=""
            if hsts.is_valid
            else "Send a Strict-Transport-Security header from your API or "
            "proxy, redeploy, then verify again.",
        ),
    ]
    if plaintext.is_valid and hsts.is_valid:
        return ValidationResult(
            is_valid=True,
            message=f"{url} refuses plain HTTP and sends HSTS.",
            task_results=task_results,
        )
    return ValidationResult(
        is_valid=False,
        verification_completed=(
            plaintext.verification_completed and hsts.verification_completed
        ),
        message=f"Your live API at {url} isn't fully locked to HTTPS yet.",
        task_results=task_results,
    )
