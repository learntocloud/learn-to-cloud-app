"""HTTP client for starting Durable verification orchestrations."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Any
from uuid import UUID

import httpx
from azure.core.exceptions import AzureError
from learn_to_cloud_shared.core.azure_auth import get_token as get_azure_token
from learn_to_cloud_shared.core.config import get_web_settings


class DurableFailureKind(StrEnum):
    """Stable categories for verification service failures."""

    CONFIGURATION = "configuration"
    AUTHENTICATION = "authentication"
    TRANSPORT = "transport"
    HTTP_RETRYABLE = "http_retryable"
    HTTP_REJECTED = "http_rejected"
    PROTOCOL = "protocol"


class DurableVerificationError(Exception):
    """Structured verification service failure."""

    def __init__(
        self,
        message: str,
        *,
        failure_kind: DurableFailureKind,
        retryable: bool,
        status_code: int | None = None,
    ) -> None:
        super().__init__(message)
        self.failure_kind = failure_kind
        self.retryable = retryable
        self.status_code = status_code

    @property
    def error_code(self) -> str:
        return f"durable_{self.failure_kind.value}_error"


class DurableVerificationConfigError(DurableVerificationError):
    """Raised when the Durable starter endpoint is not configured."""

    def __init__(self, message: str) -> None:
        super().__init__(
            message,
            failure_kind=DurableFailureKind.CONFIGURATION,
            retryable=False,
        )


class DurableVerificationStartError(DurableVerificationError):
    """Raised when the Durable starter rejects or fails a start request."""

    def __init__(
        self,
        message: str,
        *,
        failure_kind: DurableFailureKind = DurableFailureKind.TRANSPORT,
        retryable: bool = True,
        status_code: int | None = None,
    ) -> None:
        super().__init__(
            message,
            failure_kind=failure_kind,
            retryable=retryable,
            status_code=status_code,
        )


class DurableVerificationStatusError(DurableVerificationError):
    """Raised when Durable status cannot be fetched or parsed."""

    def __init__(
        self,
        message: str,
        *,
        failure_kind: DurableFailureKind = DurableFailureKind.TRANSPORT,
        retryable: bool = True,
        status_code: int | None = None,
    ) -> None:
        super().__init__(
            message,
            failure_kind=failure_kind,
            retryable=retryable,
            status_code=status_code,
        )


class DurableVerificationAuthError(DurableVerificationError):
    """Raised when a verification Function access token cannot be acquired."""

    def __init__(self, message: str) -> None:
        super().__init__(
            message,
            failure_kind=DurableFailureKind.AUTHENTICATION,
            retryable=False,
        )


def _http_failure_kind(status_code: int) -> tuple[DurableFailureKind, bool]:
    if status_code in {408, 425, 429} or status_code >= 500:
        return DurableFailureKind.HTTP_RETRYABLE, True
    return DurableFailureKind.HTTP_REJECTED, False


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
) -> DurableStartResult:
    """POST a Durable starter request and parse its ``{"id": ...}`` response."""
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.post(url, headers=headers)
    except httpx.HTTPError as exc:
        raise DurableVerificationStartError(
            "Durable starter request failed.",
            failure_kind=DurableFailureKind.TRANSPORT,
            retryable=True,
        ) from exc

    if response.status_code >= 400:
        failure_kind, retryable = _http_failure_kind(response.status_code)
        raise DurableVerificationStartError(
            f"Durable starter returned HTTP {response.status_code}",
            failure_kind=failure_kind,
            retryable=retryable,
            status_code=response.status_code,
        )

    try:
        payload = response.json()
    except ValueError as exc:
        raise DurableVerificationStartError(
            "Durable starter returned invalid JSON.",
            failure_kind=DurableFailureKind.PROTOCOL,
            retryable=False,
        ) from exc

    instance_id = payload.get("id")
    if not isinstance(instance_id, str) or not instance_id:
        raise DurableVerificationStartError(
            "Durable starter response did not include an instance ID.",
            failure_kind=DurableFailureKind.PROTOCOL,
            retryable=False,
        )

    return DurableStartResult(instance_id=instance_id)


async def start_verification_attempt_orchestration(
    attempt_id: UUID,
) -> DurableStartResult:
    """Start a Durable orchestration using only the persisted attempt ID."""
    settings = get_web_settings()
    base_url, token_scope = _verification_endpoint_config(settings)
    headers = await _verification_auth_headers(token_scope)

    url = f"{base_url}/api/verification/attempts/{attempt_id}/start"
    return await _post_start_request(
        url,
        headers=headers,
        timeout=settings.http.external_api_timeout,
    )


async def get_verification_attempt_status(
    instance_id: str,
) -> DurableStatusResult:
    """Fetch an attempt's Durable status through the Function app proxy."""
    settings = get_web_settings()
    base_url, token_scope = _verification_endpoint_config(settings)

    headers = await _verification_auth_headers(token_scope)

    url = f"{base_url}/api/verification/attempts/{instance_id}/status"

    timeout = settings.http.external_api_timeout
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.get(url, headers=headers)
    except httpx.HTTPError as exc:
        raise DurableVerificationStatusError(
            "Durable status request failed.",
            failure_kind=DurableFailureKind.TRANSPORT,
            retryable=True,
        ) from exc

    if response.status_code >= 400:
        failure_kind, retryable = _http_failure_kind(response.status_code)
        raise DurableVerificationStatusError(
            f"Durable status returned HTTP {response.status_code}",
            failure_kind=failure_kind,
            retryable=retryable,
            status_code=response.status_code,
        )

    try:
        payload = response.json()
    except ValueError as exc:
        raise DurableVerificationStatusError(
            "Durable status returned invalid JSON.",
            failure_kind=DurableFailureKind.PROTOCOL,
            retryable=False,
        ) from exc

    runtime_status = payload.get("runtimeStatus")
    if not isinstance(runtime_status, str) or not runtime_status:
        raise DurableVerificationStatusError(
            "Durable status response did not include runtimeStatus.",
            failure_kind=DurableFailureKind.PROTOCOL,
            retryable=False,
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
