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


class DurableVerificationStatusError(Exception):
    """Raised when Durable status cannot be fetched or parsed."""


@dataclass(frozen=True, slots=True)
class DurableStartResult:
    instance_id: str


@dataclass(frozen=True, slots=True)
class DurableStatusResult:
    runtime_status: str
    output: object | None = None
    custom_status: object | None = None


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


async def get_verification_orchestration_status(
    instance_id: str,
) -> DurableStatusResult:
    """Fetch Durable orchestration status through the Function app proxy."""
    settings = get_settings()
    base_url = settings.verification_functions_base_url.rstrip("/")
    function_key = settings.verification_functions_key

    if not base_url or not function_key:
        raise DurableVerificationConfigError(
            "Verification Functions endpoint is not configured."
        )

    url = f"{base_url}/api/verification/jobs/{instance_id}/status"
    headers = {"x-functions-key": function_key}

    try:
        async with httpx.AsyncClient(timeout=settings.external_api_timeout) as client:
            response = await client.get(url, headers=headers)
    except httpx.HTTPError as exc:
        raise DurableVerificationStatusError("Durable status request failed.") from exc

    if response.status_code >= 400:
        raise DurableVerificationStatusError(
            f"Durable status returned HTTP {response.status_code}"
        )

    try:
        payload = response.json()
    except ValueError as exc:
        raise DurableVerificationStatusError(
            "Durable status returned invalid JSON."
        ) from exc

    runtime_status = payload.get("runtimeStatus")
    if not isinstance(runtime_status, str) or not runtime_status:
        raise DurableVerificationStatusError(
            "Durable status response did not include runtimeStatus."
        )

    return DurableStatusResult(
        runtime_status=runtime_status,
        output=payload.get("output"),
        custom_status=payload.get("customStatus"),
    )
