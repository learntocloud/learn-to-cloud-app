"""Unit tests for the Durable verification attempt client."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import httpx
import pytest
from azure.core.exceptions import ClientAuthenticationError

from learn_to_cloud.services.durable_verification_client import (
    DurableVerificationAuthError,
    DurableVerificationConfigError,
    DurableVerificationStartError,
    DurableVerificationStatusError,
    get_verification_attempt_status,
    start_verification_attempt_orchestration,
)

pytestmark = pytest.mark.unit
_TOKEN = "-".join(("access", "token"))


def _settings(
    *,
    base_url: str = "http://localhost:7071/",
    token_scope: str = "api://verification-functions/.default",
    is_development: bool = False,
) -> SimpleNamespace:
    return SimpleNamespace(
        verification_functions=SimpleNamespace(
            base_url=base_url,
            token_scope=token_scope,
        ),
        http=SimpleNamespace(external_api_timeout=3.0),
        is_development=is_development,
    )


def _async_client(response: httpx.Response | Exception):
    client = MagicMock()
    if isinstance(response, Exception):
        client.post = AsyncMock(side_effect=response)
        client.get = AsyncMock(side_effect=response)
    else:
        client.post = AsyncMock(return_value=response)
        client.get = AsyncMock(return_value=response)

    context_manager = MagicMock()
    context_manager.__aenter__ = AsyncMock(return_value=client)
    context_manager.__aexit__ = AsyncMock(return_value=None)
    return client, context_manager


async def test_starts_attempt_orchestration_with_no_body() -> None:
    attempt_id = uuid4()
    client, context_manager = _async_client(httpx.Response(202, json={"id": "abc"}))

    with (
        patch(
            "learn_to_cloud.services.durable_verification_client.get_web_settings",
            return_value=_settings(),
        ),
        patch(
            "learn_to_cloud.services.durable_verification_client.get_azure_token",
            new=AsyncMock(return_value=_TOKEN),
        ),
        patch(
            "learn_to_cloud.services.durable_verification_client.httpx.AsyncClient",
            return_value=context_manager,
        ) as async_client,
    ):
        result = await start_verification_attempt_orchestration(attempt_id)

    assert result.instance_id == "abc"
    async_client.assert_called_once_with(timeout=3.0)
    client.post.assert_awaited_once_with(
        f"http://localhost:7071/api/verification/attempts/{attempt_id}/start",
        headers={"Authorization": f"Bearer {_TOKEN}"},
    )


async def test_start_http_error_raises_start_error() -> None:
    _, context_manager = _async_client(httpx.Response(500, json={"error": "boom"}))

    with (
        patch(
            "learn_to_cloud.services.durable_verification_client.get_web_settings",
            return_value=_settings(),
        ),
        patch(
            "learn_to_cloud.services.durable_verification_client.get_azure_token",
            new=AsyncMock(return_value=_TOKEN),
        ),
        patch(
            "learn_to_cloud.services.durable_verification_client.httpx.AsyncClient",
            return_value=context_manager,
        ),
        pytest.raises(DurableVerificationStartError, match="HTTP 500"),
    ):
        await start_verification_attempt_orchestration(uuid4())


async def test_gets_attempt_status() -> None:
    instance_id = str(uuid4())
    client, context_manager = _async_client(
        httpx.Response(200, json={"runtimeStatus": "Running", "customStatus": None})
    )

    with (
        patch(
            "learn_to_cloud.services.durable_verification_client.get_web_settings",
            return_value=_settings(),
        ),
        patch(
            "learn_to_cloud.services.durable_verification_client.get_azure_token",
            new=AsyncMock(return_value=_TOKEN),
        ),
        patch(
            "learn_to_cloud.services.durable_verification_client.httpx.AsyncClient",
            return_value=context_manager,
        ),
    ):
        result = await get_verification_attempt_status(instance_id)

    assert result.runtime_status == "Running"
    client.get.assert_awaited_once_with(
        f"http://localhost:7071/api/verification/attempts/{instance_id}/status",
        headers={"Authorization": f"Bearer {_TOKEN}"},
    )


async def test_status_without_runtime_status_raises_status_error() -> None:
    _, context_manager = _async_client(httpx.Response(200, json={"output": {}}))

    with (
        patch(
            "learn_to_cloud.services.durable_verification_client.get_web_settings",
            return_value=_settings(),
        ),
        patch(
            "learn_to_cloud.services.durable_verification_client.get_azure_token",
            new=AsyncMock(return_value="access-token"),
        ),
        patch(
            "learn_to_cloud.services.durable_verification_client.httpx.AsyncClient",
            return_value=context_manager,
        ),
        pytest.raises(DurableVerificationStatusError, match="runtimeStatus"),
    ):
        await get_verification_attempt_status(str(uuid4()))


async def test_production_requires_token_scope() -> None:
    with (
        patch(
            "learn_to_cloud.services.durable_verification_client.get_web_settings",
            return_value=_settings(token_scope=""),
        ),
        pytest.raises(DurableVerificationConfigError),
    ):
        await start_verification_attempt_orchestration(uuid4())


async def test_token_failure_raises_auth_error() -> None:
    with (
        patch(
            "learn_to_cloud.services.durable_verification_client.get_web_settings",
            return_value=_settings(),
        ),
        patch(
            "learn_to_cloud.services.durable_verification_client.get_azure_token",
            new=AsyncMock(side_effect=ClientAuthenticationError("bad token")),
        ),
        pytest.raises(DurableVerificationAuthError),
    ):
        await start_verification_attempt_orchestration(uuid4())
