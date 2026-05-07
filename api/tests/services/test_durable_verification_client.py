"""Unit tests for the Durable verification starter client."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import httpx
import pytest

from learn_to_cloud.services.durable_verification_client import (
    DurableVerificationConfigError,
    DurableVerificationStartError,
    DurableVerificationStatusError,
    get_verification_orchestration_status,
    start_verification_orchestration,
)

pytestmark = pytest.mark.unit


def _settings(
    *,
    base_url: str = "http://localhost:7071/",
    key: str = "function-key",
) -> SimpleNamespace:
    return SimpleNamespace(
        verification_functions_base_url=base_url,
        verification_functions_key=key,
        external_api_timeout=3.0,
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


async def test_starts_orchestration_with_function_key_header():
    job_id = uuid4()
    client, context_manager = _async_client(httpx.Response(202, json={"id": "abc"}))

    with (
        patch(
            "learn_to_cloud.services.durable_verification_client.get_settings",
            return_value=_settings(),
        ),
        patch(
            "learn_to_cloud.services.durable_verification_client.httpx.AsyncClient",
            return_value=context_manager,
        ) as async_client,
    ):
        result = await start_verification_orchestration(job_id)

    assert result.instance_id == "abc"
    async_client.assert_called_once_with(timeout=3.0)
    client.post.assert_awaited_once_with(
        f"http://localhost:7071/api/verification/jobs/{job_id}/start",
        headers={"x-functions-key": "function-key"},
    )


async def test_missing_config_fails_before_http_call():
    with (
        patch(
            "learn_to_cloud.services.durable_verification_client.get_settings",
            return_value=_settings(base_url="", key=""),
        ),
        patch(
            "learn_to_cloud.services.durable_verification_client.httpx.AsyncClient"
        ) as async_client,
        pytest.raises(DurableVerificationConfigError),
    ):
        await start_verification_orchestration(uuid4())

    async_client.assert_not_called()


async def test_http_error_status_raises_start_error():
    _, context_manager = _async_client(httpx.Response(500, json={"error": "boom"}))

    with (
        patch(
            "learn_to_cloud.services.durable_verification_client.get_settings",
            return_value=_settings(),
        ),
        patch(
            "learn_to_cloud.services.durable_verification_client.httpx.AsyncClient",
            return_value=context_manager,
        ),
        pytest.raises(DurableVerificationStartError, match="HTTP 500"),
    ):
        await start_verification_orchestration(uuid4())


async def test_transport_error_raises_start_error():
    request = httpx.Request("POST", "http://localhost:7071")
    _, context_manager = _async_client(httpx.ConnectError("down", request=request))

    with (
        patch(
            "learn_to_cloud.services.durable_verification_client.get_settings",
            return_value=_settings(),
        ),
        patch(
            "learn_to_cloud.services.durable_verification_client.httpx.AsyncClient",
            return_value=context_manager,
        ),
        pytest.raises(DurableVerificationStartError, match="request failed"),
    ):
        await start_verification_orchestration(uuid4())


async def test_gets_orchestration_status_with_function_key_header():
    instance_id = str(uuid4())
    client, context_manager = _async_client(
        httpx.Response(200, json={"runtimeStatus": "Running", "customStatus": None})
    )

    with (
        patch(
            "learn_to_cloud.services.durable_verification_client.get_settings",
            return_value=_settings(),
        ),
        patch(
            "learn_to_cloud.services.durable_verification_client.httpx.AsyncClient",
            return_value=context_manager,
        ) as async_client,
    ):
        result = await get_verification_orchestration_status(instance_id)

    assert result.runtime_status == "Running"
    async_client.assert_called_once_with(timeout=3.0)
    client.get.assert_awaited_once_with(
        f"http://localhost:7071/api/verification/jobs/{instance_id}/status",
        headers={"x-functions-key": "function-key"},
    )


async def test_status_without_runtime_status_raises_status_error():
    _, context_manager = _async_client(httpx.Response(200, json={"output": {}}))

    with (
        patch(
            "learn_to_cloud.services.durable_verification_client.get_settings",
            return_value=_settings(),
        ),
        patch(
            "learn_to_cloud.services.durable_verification_client.httpx.AsyncClient",
            return_value=context_manager,
        ),
        pytest.raises(DurableVerificationStatusError, match="runtimeStatus"),
    ):
        await get_verification_orchestration_status(str(uuid4()))
