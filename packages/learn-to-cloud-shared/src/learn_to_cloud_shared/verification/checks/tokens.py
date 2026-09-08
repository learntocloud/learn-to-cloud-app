"""Typed tokens checks for verification workflows."""

from __future__ import annotations

from learn_to_cloud_shared.submission_values import TokenValue
from learn_to_cloud_shared.verification.checks.common import validation_step_result
from learn_to_cloud_shared.verification.core import StepContext, StepResult
from learn_to_cloud_shared.verification.token_base import (
    verify_ctf_token,
    verify_networking_token,
)


async def check_ctf_token(context: StepContext) -> StepResult:
    """Deterministic Phase 1 gate: verify the submitted CTF token."""
    submitted_value = context.submitted_value
    if not isinstance(submitted_value, TokenValue):
        raise TypeError("CTF check requires a token value")
    result = verify_ctf_token(submitted_value.token, context.job.github_username or "")
    return validation_step_result(result)


async def check_networking_token(context: StepContext) -> StepResult:
    """Deterministic Phase 2 gate: verify the submitted networking token."""
    submitted_value = context.submitted_value
    if not isinstance(submitted_value, TokenValue):
        raise TypeError("Networking check requires a token value")
    result = verify_networking_token(
        submitted_value.token, context.job.github_username or ""
    )
    return validation_step_result(result)
