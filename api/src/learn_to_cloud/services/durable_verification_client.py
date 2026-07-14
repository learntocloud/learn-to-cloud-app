"""HTTP client for starting Durable verification orchestrations."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from uuid import UUID

import httpx
from azure.core.exceptions import AzureError
from learn_to_cloud_shared.core.azure_auth import get_token as get_azure_token
from learn_to_cloud_shared.core.config import get_web_settings
from learn_to_cloud_shared.verification_job_executor import PreparedVerificationJob


class DurableVerificationConfigError(Exception):
    """Raised when the Durable starter endpoint is not configured."""


class DurableVerificationStartError(Exception):
    """Raised when the Durable starter rejects or fails a start request."""


class DurableVerificationStatusError(Exception):
    """Raised when Durable status cannot be fetched or parsed."""


class DurableVerificationAuthError(Exception):
    """Raised when a verification Function access token cannot be acquired."""


@dataclass(frozen=True, slots=True)
class DurableStartResult:
    instance_id: str


@dataclass(frozen=True, slots=True)
class DurableStatusResult:
    runtime_status: str
    output: object | None = None
    custom_status: object | None = None


async def _post_start_request(
    url: str,
    *,
    headers: dict[str, str],
    timeout: float,
    body: dict[str, Any] | None,
) -> DurableStartResult:
    """POST a Durable starter request and parse its ``{"id": ...}`` response."""
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            if body is None:
                response = await client.post(url, headers=headers)
            else:
                response = await client.post(url, headers=headers, json=body)
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


async def start_verification_orchestration(
    prepared: PreparedVerificationJob,
) -> DurableStartResult:
    """Start the legacy Durable orchestration for a persisted verification job.

    Posts the full :class:`PreparedVerificationJob` payload to the
    Functions starter so the orchestration has everything it needs to
    run without reading curriculum tables. The Functions side still
    validates the immutable fields (``user_id``, ``requirement_uuid``,
    ``submitted_value``) against the ``verification_jobs`` row before
    starting -- the payload is trusted only for the requirement
    *definition* and ``github_username`` snapshot.

    New submissions no longer call this -- see
    :func:`start_verification_attempt_orchestration`. This stays registered
    for any in-flight legacy instances until PR8 (legacy-drain).
    """
    settings = get_web_settings()
    base_url, token_scope = _verification_endpoint_config(settings)
    headers = await _verification_auth_headers(token_scope)

    url = f"{base_url}/api/verification/jobs/{prepared.id}/start"
    return await _post_start_request(
        url,
        headers=headers,
        timeout=settings.http.external_api_timeout,
        body=prepared.to_payload(),
    )


async def start_verification_attempt_orchestration(
    attempt_id: UUID,
) -> DurableStartResult:
    """Start the versioned Durable attempt orchestration for a persisted attempt.

    Posts no body: the Functions starter loads identity, the requirement
    snapshot, and the submitted value straight from the ``verification_attempts``
    row (see the PR4 bridge), so the API never sends -- and the narrowed
    Functions role never needs to trust -- a second copy of any of that.
    """
    settings = get_web_settings()
    base_url, token_scope = _verification_endpoint_config(settings)
    headers = await _verification_auth_headers(token_scope)

    url = f"{base_url}/api/verification/attempts/{attempt_id}/start"
    return await _post_start_request(
        url,
        headers=headers,
        timeout=settings.http.external_api_timeout,
        body=None,
    )


async def get_verification_orchestration_status(
    instance_id: str,
) -> DurableStatusResult:
    """Fetch Durable orchestration status through the Function app proxy."""
    settings = get_web_settings()
    base_url, token_scope = _verification_endpoint_config(settings)

    headers = await _verification_auth_headers(token_scope)

    url = f"{base_url}/api/verification/jobs/{instance_id}/status"

    timeout = settings.http.external_api_timeout
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
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


def _verification_endpoint_config(settings: Any) -> tuple[str, str | None]:
    base_url = settings.verification_functions.base_url.rstrip("/")

    if not base_url:
        raise DurableVerificationConfigError(
            "Verification Functions endpoint is not configured."
        )

    # The local Functions host runs with AuthLevel.ANONYMOUS, so no bearer token
    # is needed (or obtainable) in development. Everywhere else the API
    # authenticates with a managed-identity token for the configured scope.
    if settings.is_development:
        return base_url, None

    token_scope = settings.verification_functions.token_scope
    if not token_scope:
        raise DurableVerificationConfigError(
            "Verification Functions endpoint is not configured."
        )

    return base_url, token_scope


async def _verification_auth_headers(token_scope: str | None) -> dict[str, str]:
    if token_scope is None:
        return {}
    token = await _get_verification_token(token_scope)
    return {"Authorization": f"Bearer {token}"}


async def _get_verification_token(token_scope: str) -> str:
    try:
        return await get_azure_token(token_scope)
    except AzureError as exc:
        raise DurableVerificationAuthError(
            "Verification Functions access token could not be acquired."
        ) from exc
