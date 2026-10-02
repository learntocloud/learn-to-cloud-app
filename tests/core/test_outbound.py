"""Outbound dependency taxonomy, metric, and per-dependency failure drills."""

from __future__ import annotations

import asyncio
import logging
import socket
import ssl
from unittest.mock import AsyncMock, Mock, patch

import asyncpg
import httpx
import openai
import pytest
from azure.core.exceptions import ClientAuthenticationError, ServiceRequestError
from azure.identity import CredentialUnavailableError
from opentelemetry.instrumentation.httpx import AsyncOpenTelemetryTransport
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
from opentelemetry.trace import SpanKind, StatusCode
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.pool import NullPool
from tenacity import retry, retry_if_exception_type, stop_after_attempt

from learn_to_cloud.core import database, github_client
from learn_to_cloud.core.azure_auth import MeasuredCredential
from learn_to_cloud.core.config import DatabaseConfig
from learn_to_cloud.core.outbound import (
    DEPENDENCY_ATTEMPT,
    DEPENDENCY_NAME,
    DEPENDENCY_OPERATION,
    ERROR_TYPE,
    ERROR_TYPES,
    OTHER,
    Dependency,
    MeasuredTransport,
    classify,
    classify_status,
    outbound_call,
    sanitize_url,
    track_retry_attempt,
)
from learn_to_cloud.verification import deployed_api
from tests.support.telemetry import capture_outbound_telemetry

SECRET = "sentinel-secret-7f3a"


@pytest.fixture
def telemetry():
    with capture_outbound_telemetry() as captured:
        yield captured
    captured.assert_bounded()


def _request() -> httpx.Request:
    return httpx.Request("GET", "https://api.example.com/x")


class TestClassify:
    @pytest.mark.parametrize(
        ("exc", "expected"),
        [
            (httpx.ConnectTimeout("x"), "timeout.connect"),
            (httpx.ReadTimeout("x"), "timeout.read"),
            (httpx.WriteTimeout("x"), "timeout.write"),
            (httpx.PoolTimeout("x"), "timeout.pool"),
            (httpx.ConnectError("x"), "connection"),
            (httpx.RemoteProtocolError("x"), "connection"),
            (socket.gaierror(-2, "Name or service not known"), "dns"),
            (ssl.SSLError("bad cert"), "tls"),
            (asyncio.CancelledError(), "cancelled"),
            (TimeoutError(), "timeout"),
            (ConnectionResetError(), "connection"),
            (openai.APITimeoutError(request=_request()), "timeout"),
            (openai.APIConnectionError(request=_request()), "connection"),
            (ClientAuthenticationError("x"), "auth"),
            (CredentialUnavailableError("x"), "auth"),
            (ServiceRequestError("x"), "connection"),
            (asyncpg.InvalidPasswordError("x"), "auth"),
            (asyncpg.QueryCanceledError("x"), "timeout"),
            (asyncpg.ConnectionDoesNotExistError("x"), "connection"),
            (ValueError("x"), OTHER),
        ],
    )
    def test_maps_library_errors_to_bounded_types(self, exc, expected):
        assert classify(exc) == expected
        assert expected in ERROR_TYPES

    @pytest.mark.parametrize("status", [429, 500, 401])
    def test_maps_openai_status_errors(self, status):
        response = httpx.Response(status, request=_request())
        exc = openai.APIStatusError("x", response=response, body=None)
        assert classify(exc) == classify_status(status)

    def test_specific_cause_wins_over_generic_wrapper(self):
        try:
            try:
                raise httpx.ConnectTimeout("x")
            except httpx.ConnectTimeout as inner:
                raise openai.APITimeoutError(request=_request()) from inner
        except openai.APITimeoutError as exc:
            assert classify(exc) == "timeout.connect"

    def test_dns_cause_wins_over_connect_error(self):
        exc = httpx.ConnectError("x")
        exc.__cause__ = socket.gaierror(-2, "unknown host")
        assert classify(exc) == "dns"

    def test_self_referencing_chain_terminates(self):
        exc = ValueError("loop")
        exc.__context__ = exc
        assert classify(exc) == OTHER

    @pytest.mark.parametrize(
        ("status", "headers", "expected"),
        [
            (200, None, None),
            (304, None, None),
            (404, None, "http_4xx"),
            (401, None, "auth"),
            (407, None, "auth"),
            (429, None, "rate_limit"),
            (403, {"x-ratelimit-remaining": "0"}, "rate_limit"),
            (403, {"retry-after": "10"}, "rate_limit"),
            (403, {"x-ratelimit-remaining": "5"}, "http_4xx"),
            (502, None, "http_5xx"),
        ],
    )
    def test_classify_status(self, status, headers, expected):
        assert classify_status(status, headers) == expected


@pytest.mark.parametrize(
    ("url", "expected"),
    [
        (
            f"https://user:{SECRET}@api.example.com:8443/a/b?token={SECRET}#{SECRET}",
            "https://api.example.com:8443/a/b",
        ),
        ("http://[::1]:8080/x?y=1", "http://[::1]:8080/x"),
        ("https://example.com", "https://example.com"),
    ],
)
def test_sanitize_url_drops_credentials_query_and_fragment(url, expected):
    assert sanitize_url(url) == expected


def _client(dependency: Dependency, handler) -> httpx.AsyncClient:
    return httpx.AsyncClient(
        transport=MeasuredTransport(dependency, httpx.MockTransport(handler))
    )


@pytest.mark.parametrize(
    ("dependency", "failure", "expected"),
    [
        (Dependency.GITHUB, httpx.ReadTimeout, "timeout.read"),
        (Dependency.GITHUB, httpx.ConnectTimeout, "timeout.connect"),
        (Dependency.GITHUB, 503, "http_5xx"),
        (Dependency.GITHUB, 429, "rate_limit"),
        (Dependency.DEPLOYED_API, httpx.ReadTimeout, "timeout.read"),
        (Dependency.DEPLOYED_API, httpx.ConnectError, "connection"),
        (Dependency.DEPLOYED_API, 500, "http_5xx"),
    ],
)
async def test_http_dependency_failure_drill(telemetry, dependency, failure, expected):
    def handler(request: httpx.Request) -> httpx.Response:
        if isinstance(failure, int):
            return httpx.Response(failure)
        raise failure("boom", request=request)

    async with _client(dependency, handler) as client:
        if isinstance(failure, int):
            response = await client.get(f"https://api.example.com/repos?token={SECRET}")
            assert response.status_code == failure
        else:
            with pytest.raises(failure):
                await client.get(f"https://api.example.com/repos?token={SECRET}")

    (span,) = telemetry.spans()
    assert span.kind is SpanKind.CLIENT
    assert span.name == "GET"
    assert span.status.status_code is StatusCode.ERROR
    assert span.attributes[ERROR_TYPE] == expected
    assert span.attributes[DEPENDENCY_NAME] == dependency.value
    assert span.attributes["url.full"] == "https://api.example.com/repos"
    (point,) = telemetry.points()
    assert point[ERROR_TYPE] == expected
    assert point[DEPENDENCY_NAME] == dependency.value
    assert point[DEPENDENCY_OPERATION] == "GET"
    assert point[DEPENDENCY_ATTEMPT] == "first"
    assert SECRET not in telemetry.dump()


async def test_http_success_records_metric_without_error(telemetry):
    async with _client(Dependency.GITHUB, lambda _: httpx.Response(200)) as client:
        await client.get("https://api.example.com/")

    (span,) = telemetry.spans()
    assert span.status.status_code is StatusCode.UNSET
    assert ERROR_TYPE not in span.attributes
    (point,) = telemetry.points()
    assert ERROR_TYPE not in point
    assert point["http.response.status_code"] == 200


async def test_retries_are_marked_on_span_and_metric(telemetry):
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        if calls == 1:
            raise httpx.ReadTimeout("slow", request=request)
        return httpx.Response(200)

    async with _client(Dependency.GITHUB, handler) as client:

        @retry(
            stop=stop_after_attempt(2),
            retry=retry_if_exception_type(httpx.ReadTimeout),
            before=track_retry_attempt,
        )
        async def fetch() -> httpx.Response:
            return await client.get("https://api.example.com/")

        await fetch()

    first, second = telemetry.spans()
    assert "http.request.resend_count" not in first.attributes
    assert second.attributes["http.request.resend_count"] == 1
    by_attempt = {point[DEPENDENCY_ATTEMPT]: point for point in telemetry.points()}
    assert by_attempt["first"][ERROR_TYPE] == "timeout.read"
    assert ERROR_TYPE not in by_attempt["retry"]


async def test_measured_transport_suppresses_duplicate_httpx_spans(telemetry):

    native = InMemorySpanExporter()
    provider = TracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(native))
    inner = AsyncOpenTelemetryTransport(
        httpx.MockTransport(lambda _: httpx.Response(200)), tracer_provider=provider
    )
    async with httpx.AsyncClient(
        transport=MeasuredTransport(Dependency.GITHUB, inner)
    ) as client:
        await client.get("https://api.example.com/")

    assert len(telemetry.spans()) == 1
    assert native.get_finished_spans() == ()
    provider.shutdown()


@pytest.mark.parametrize(
    ("builder", "dependency"),
    [
        (github_client._build_github_client, Dependency.GITHUB),
        (deployed_api._build_deployed_api_client, Dependency.DEPLOYED_API),
    ],
)
async def test_runtime_http_clients_use_the_measured_transport(builder, dependency):
    client = builder()
    try:
        transport = client._transport
        assert isinstance(transport, MeasuredTransport)
        assert transport._dependency is dependency
    finally:
        await client.aclose()


async def test_foundry_failure_drill(telemetry):
    try:
        raise httpx.ReadTimeout("slow")
    except httpx.ReadTimeout as cause:
        error = openai.APITimeoutError(request=_request())
        error.__cause__ = cause

    with pytest.raises(openai.APITimeoutError):
        async with outbound_call(Dependency.FOUNDRY, "responses"):
            raise error

    assert telemetry.spans() == []
    (point,) = telemetry.points()
    assert point[DEPENDENCY_NAME] == "foundry"
    assert point[ERROR_TYPE] == "timeout.read"


async def test_entra_failure_drill(telemetry):
    inner = Mock(spec=["get_token", "close"])
    inner.get_token = AsyncMock(side_effect=ClientAuthenticationError(SECRET))
    inner.close = AsyncMock()
    credential = MeasuredCredential(inner)

    with pytest.raises(ClientAuthenticationError):
        await credential.get_token("scope")
    with pytest.raises(ClientAuthenticationError):
        await credential.get_token_info("scope")

    points = telemetry.points()
    assert [p[DEPENDENCY_NAME] for p in points] == ["entra"]
    assert points[0]["count"] == 2
    assert points[0][ERROR_TYPE] == "auth"
    assert SECRET not in telemetry.dump()


def _azure_settings() -> DatabaseConfig:
    return DatabaseConfig(user="app", host="db.example.com", name="app")


async def test_postgres_connect_failure_drill(telemetry, caplog):
    caplog.set_level(logging.ERROR, logger=database.logger.name)
    with (
        patch.object(database, "_get_azure_token", AsyncMock(return_value=SECRET)),
        patch.object(
            database.asyncpg, "connect", AsyncMock(side_effect=TimeoutError(SECRET))
        ),
        pytest.raises(TimeoutError),
    ):
        await database._azure_asyncpg_creator(_azure_settings())

    (span,) = telemetry.spans()
    assert span.kind is SpanKind.CLIENT
    assert span.name == "connect"
    assert span.status.status_code is StatusCode.ERROR
    assert span.attributes[ERROR_TYPE] == "timeout"
    (point,) = telemetry.points()
    assert point[DEPENDENCY_OPERATION] == "connect"
    assert point[ERROR_TYPE] == "timeout"
    (record,) = [r for r in caplog.records if r.getMessage() == "db.connection.failed"]
    assert getattr(record, "error.type") == "timeout"
    assert getattr(record, DEPENDENCY_NAME) == "postgres"
    assert SECRET not in telemetry.dump()
    assert SECRET not in caplog.text


@pytest.mark.integration
async def test_postgres_statement_failure_drill(telemetry, test_engine):
    engine = create_async_engine(test_engine.url, poolclass=NullPool)
    database.measure_statements(engine)
    async with engine.connect() as conn:
        await conn.execute(text("SELECT 1"))
        with pytest.raises(Exception, match="canceling statement"):
            await conn.execute(text("SET LOCAL statement_timeout = 10"))
            await conn.execute(text(f"SELECT pg_sleep(1), '{SECRET}'"))

    await engine.dispose()

    points = [p for p in telemetry.points() if p[DEPENDENCY_OPERATION] == "SELECT"]
    assert {p.get(ERROR_TYPE) for p in points} == {None, "timeout"}
    assert SECRET not in telemetry.dump()
