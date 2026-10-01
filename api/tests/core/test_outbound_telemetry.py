"""Failure drills for the API's own outbound boundaries: GitHub OAuth and Foundry."""

from __future__ import annotations

import logging
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import httpx
import httpx2
import openai
import pytest
from fastapi.responses import RedirectResponse
from learn_to_cloud_shared.core.config import OAuthConfig
from learn_to_cloud_shared.core.outbound import (
    DEPENDENCY_NAME,
    DEPENDENCY_OPERATION,
    ERROR_TYPE,
)
from learn_to_cloud_shared_test_support.telemetry import capture_outbound_telemetry
from opentelemetry.trace import SpanKind, StatusCode

from learn_to_cloud.core.auth import init_oauth, oauth, oauth_transport
from learn_to_cloud.routes import auth_routes
from learn_to_cloud.services import verification_grader

SECRET = "sentinel-secret-7f3a"
TOKEN_URL = "https://github.com/login/oauth/access_token"


@pytest.fixture
def telemetry():
    with capture_outbound_telemetry() as captured:
        yield captured
    captured.assert_bounded()


@pytest.fixture
def github(monkeypatch):
    """A real authlib GitHub client whose shared transport talks to ``routes``."""
    routes: dict[str, httpx2.Response | type[httpx2.RequestError]] = {}

    def handle(request: httpx2.Request) -> httpx2.Response:
        outcome = routes[str(request.url.copy_with(query=None))]
        if isinstance(outcome, httpx2.Response):
            return outcome
        raise outcome("boom", request=request)

    monkeypatch.setattr(oauth_transport, "_inner", httpx2.MockTransport(handle))
    oauth._clients.pop("github", None)
    init_oauth(OAuthConfig(client_id="client-id", client_secret=SECRET))
    client = oauth.create_client("github")

    async def authorize_access_token(_request):
        return await client.fetch_access_token(
            code=SECRET, redirect_uri="https://app.example.com/auth/callback"
        )

    monkeypatch.setattr(client, "authorize_access_token", authorize_access_token)
    yield routes
    oauth._clients.pop("github", None)


def _request() -> MagicMock:
    request = MagicMock()
    request.session = {}
    return request


def _log(caplog: pytest.LogCaptureFixture, message: str) -> logging.LogRecord:
    (record,) = [r for r in caplog.records if r.getMessage() == message]
    return record


async def test_oauth_token_exchange_timeout_drill(github, telemetry, caplog):
    github[TOKEN_URL] = httpx2.ReadTimeout

    result = await auth_routes.callback(_request())

    assert isinstance(result, RedirectResponse)
    (span,) = telemetry.spans()
    assert span.kind is SpanKind.CLIENT
    assert span.name == "POST"
    assert span.status.status_code is StatusCode.ERROR
    assert span.attributes["url.full"] == TOKEN_URL
    assert span.attributes[ERROR_TYPE] == "timeout.read"
    (point,) = telemetry.points()
    assert point[DEPENDENCY_NAME] == "github_oauth"
    assert point[DEPENDENCY_OPERATION] == "POST"
    assert point[ERROR_TYPE] == "timeout.read"
    record = _log(caplog, "auth.callback.token_exchange_failed")
    assert getattr(record, "error.type") == "timeout.read"
    assert getattr(record, DEPENDENCY_NAME) == "github_oauth"
    assert SECRET not in telemetry.dump()
    assert SECRET not in caplog.text


async def test_oauth_profile_fetch_outage_drill(github, telemetry, caplog):
    github[TOKEN_URL] = httpx2.Response(
        200, json={"access_token": SECRET, "token_type": "bearer"}
    )
    github["https://api.github.com/user"] = httpx2.Response(503)

    result = await auth_routes.callback(_request())

    assert isinstance(result, RedirectResponse)
    exchange, profile = telemetry.spans()
    assert exchange.status.status_code is StatusCode.UNSET
    assert profile.attributes[ERROR_TYPE] == "http_5xx"
    assert profile.attributes["http.response.status_code"] == 503
    by_operation = {p[DEPENDENCY_OPERATION]: p for p in telemetry.points()}
    assert ERROR_TYPE not in by_operation["POST"]
    assert by_operation["GET"][ERROR_TYPE] == "http_5xx"
    record = _log(caplog, "auth.callback.profile_fetch_failed")
    assert getattr(record, "error.type") == "http_5xx"
    assert SECRET not in telemetry.dump()
    assert SECRET not in caplog.text


async def test_oauth_transport_survives_authlib_closing_its_client(github):
    github["https://api.github.com/user"] = httpx2.Response(200, json={})
    client = oauth.create_client("github")

    for _ in range(2):
        response = await client.get("user", token={"access_token": "t"})
        assert response.status_code == 200


async def test_foundry_grading_timeout_drill(monkeypatch, telemetry, caplog):
    cause = httpx.ConnectTimeout("slow")
    error = openai.APITimeoutError(request=httpx.Request("POST", "https://x"))
    error.__cause__ = cause
    grader = SimpleNamespace(run=AsyncMock(side_effect=error))
    monkeypatch.setattr(
        verification_grader,
        "get_verification_grader",
        AsyncMock(return_value=grader),
    )

    with pytest.raises(verification_grader.LLMGradingError):
        await verification_grader.grade_evidence(f"grade this: {SECRET}")

    assert telemetry.spans() == []
    (point,) = telemetry.points()
    assert point[DEPENDENCY_NAME] == "foundry"
    assert point[DEPENDENCY_OPERATION] == "responses"
    assert point[ERROR_TYPE] == "timeout.connect"
    assert SECRET not in telemetry.dump()
    assert SECRET not in caplog.text
