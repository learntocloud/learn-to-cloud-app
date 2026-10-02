"""Failure drills for GitHub OAuth requests traced by the httpx2 instrumentor."""

from __future__ import annotations

import json
import logging
from collections.abc import Iterator
from unittest.mock import AsyncMock, MagicMock

import httpcore2
import pytest
from fastapi.responses import RedirectResponse
from opentelemetry.instrumentation.httpx import HTTPX2ClientInstrumentor
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
from opentelemetry.trace import SpanKind, StatusCode

from learn_to_cloud.core.auth import init_oauth, oauth
from learn_to_cloud.core.config import OAuthConfig
from learn_to_cloud.routes import auth_routes

SECRET = "sentinel-secret-7f3a"
TOKEN_URL = "https://github.com/login/oauth/access_token"


@pytest.fixture
def oauth_spans() -> Iterator[InMemorySpanExporter]:
    """Spans from the global httpx2 instrumentor that traces authlib's requests."""
    exporter = InMemorySpanExporter()
    provider = TracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    instrumentor = HTTPX2ClientInstrumentor()
    instrumentor.instrument(tracer_provider=provider)
    try:
        yield exporter
    finally:
        instrumentor.uninstrument()
        provider.shutdown()


@pytest.fixture
def github(monkeypatch):
    """A real authlib GitHub client whose connection pool answers from ``routes``."""
    routes: dict[str, httpcore2.Response | type[httpcore2.TimeoutException]] = {}

    def handle(request: httpcore2.Request) -> httpcore2.Response:
        url = request.url
        path = url.target.decode().split("?", 1)[0]
        outcome = routes[f"{url.scheme.decode()}://{url.host.decode()}{path}"]
        if isinstance(outcome, httpcore2.Response):
            return outcome
        raise outcome("boom")

    monkeypatch.setattr(
        httpcore2.AsyncConnectionPool,
        "handle_async_request",
        AsyncMock(side_effect=handle),
    )
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


def _spans_json(exporter: InMemorySpanExporter) -> str:
    return json.dumps(
        [json.loads(span.to_json()) for span in exporter.get_finished_spans()]
    )


async def test_oauth_token_exchange_timeout_drill(github, oauth_spans, caplog):
    github[TOKEN_URL] = httpcore2.ReadTimeout

    result = await auth_routes.callback(_request())

    assert isinstance(result, RedirectResponse)
    (span,) = oauth_spans.get_finished_spans()
    assert span.kind is SpanKind.CLIENT
    assert span.name == "POST"
    assert span.status.status_code is StatusCode.ERROR
    record = _log(caplog, "auth.callback.token_exchange_failed")
    assert getattr(record, "error.type") == "ReadTimeout"
    assert SECRET not in _spans_json(oauth_spans)
    assert SECRET not in caplog.text


async def test_oauth_profile_fetch_outage_drill(github, oauth_spans, caplog):
    github[TOKEN_URL] = httpcore2.Response(
        200,
        headers=[(b"content-type", b"application/json")],
        content=json.dumps({"access_token": SECRET, "token_type": "bearer"}).encode(),
    )
    github["https://api.github.com/user"] = httpcore2.Response(503, content=b"")

    result = await auth_routes.callback(_request())

    assert isinstance(result, RedirectResponse)
    exchange, profile = oauth_spans.get_finished_spans()
    assert exchange.status.status_code is StatusCode.UNSET
    assert profile.kind is SpanKind.CLIENT
    assert profile.status.status_code is StatusCode.ERROR
    record = _log(caplog, "auth.callback.profile_fetch_failed")
    assert getattr(record, "error.type") == "503"
    assert SECRET not in _spans_json(oauth_spans)
    assert SECRET not in caplog.text
