"""HTTP client for starting Durable verification orchestrations."""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

import httpx
from learn_to_cloud_shared.core.config import get_settings


class DurableVerificationConfigError(Exception):
    """Raised when the Durable starter endpoint is not configured."""


class DurableVerificationStartError(Exception):
    """Raised when the Durable starter rejects or fails a start request."""


@dataclass(frozen=True, slots=True)
class DurableStartResult:
    instance_id: str


async def start_verification_orchestration(job_id: UUID) -> DurableStartResult:
    """Start the Durable orchestration for a persisted verification job."""
    settings = get_settings()
    base_url = settings.verification_functions_base_url.rstrip("/")
    function_key = settings.verification_functions_key

    if not base_url or not function_key:
        raise DurableVerificationConfigError(
            "Verification Functions endpoint is not configured."
        )

    url = f"{base_url}/api/verification/jobs/{job_id}/start"
    headers = {"x-functions-key": function_key}

    try:
        async with httpx.AsyncClient(timeout=settings.external_api_timeout) as client:
            response = await client.post(url, headers=headers)
    except httpx.HTTPError as exc:
        raise DurableVerificationStartError("Durable starter request failed.") from exc

    if response.status_code >= 400:
        raise DurableVerificationStartError(
            f"Durable starter returned HTTP {response.status_code}"
        )

    try:
        payload = response.json()
    except ValueError as exc:
        raise DurableVerificationStartError(
            "Durable starter returned invalid JSON."
        ) from exc

    instance_id = payload.get("id")
    if not isinstance(instance_id, str) or not instance_id:
        raise DurableVerificationStartError(
            "Durable starter response did not include an instance ID."
        )

    return DurableStartResult(instance_id=instance_id)
