"""Exported PostgreSQL failure telemetry and committed-cookie boundaries."""

import logging
from unittest.mock import AsyncMock, patch

import httpx2
import pytest
from learn_to_cloud_shared.core.logger import _json_formatter
from learn_to_cloud_shared.models import AuthSession, User
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.instrumentation.logging.handler import LoggingHandler
from opentelemetry.instrumentation.sqlalchemy import SQLAlchemyInstrumentor
from opentelemetry.sdk._logs import LoggerProvider
from opentelemetry.sdk._logs.export import (
    InMemoryLogRecordExporter,
    SimpleLogRecordProcessor,
)
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
from opentelemetry.trace import SpanKind, StatusCode
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from learn_to_cloud.core.session_cookies import AUTH_COOKIE_NAME, token_digest
from tests.routes.test_session_lifecycle import browser, build_app, csrf, mint

pytestmark = pytest.mark.integration


@pytest.mark.parametrize(
    "operation", ["lookup", "create", "commit", "logout", "global", "delete"]
)
async def test_postgres_failure_telemetry_has_no_session_credentials(
    test_engine,
    test_settings,
    caplog,
    operation,
):
    engine = create_async_engine(test_settings.database.url, hide_parameters=True)
    app = build_app(engine, test_settings)
    async with app.state.session_maker() as db, db.begin():
        db.add(User(id=42, github_username="private-session-username"))
    token = await mint(app, test_settings)
    digest = token_digest(token)
    assert digest is not None
    span_exporter = InMemorySpanExporter()
    trace_provider = TracerProvider()
    trace_provider.add_span_processor(SimpleSpanProcessor(span_exporter))
    log_exporter = InMemoryLogRecordExporter()
    log_provider = LoggerProvider()
    log_provider.add_log_record_processor(SimpleLogRecordProcessor(log_exporter))
    handler = LoggingHandler(logger_provider=log_provider)
    root = logging.getLogger()
    root.addHandler(handler)
    instrumentor = SQLAlchemyInstrumentor()
    instrumentor.instrument(engine=engine.sync_engine, tracer_provider=trace_provider)
    FastAPIInstrumentor.instrument_app(app, tracer_provider=trace_provider)
    caplog.set_level(logging.INFO)
    github = AsyncMock()
    github.authorize_access_token.return_value = {"access_token": "private-oauth-token"}
    github.get.return_value = httpx2.Response(
        200,
        json={"id": 42, "login": "private-session-username"},
        request=httpx2.Request("GET", "https://api.github.com/user"),
    )
    try:
        async with browser(app, token, raise_errors=False) as client:
            confirmation = await csrf(client)
            async with engine.begin() as conn:
                await conn.execute(
                    text(
                        "CREATE FUNCTION reject_session_test() RETURNS trigger "
                        "LANGUAGE plpgsql AS $$ BEGIN "
                        "RAISE EXCEPTION 'Session store unavailable' "
                        "USING ERRCODE = 'P0001'; "
                        "END $$"
                    )
                )
                if operation == "commit":
                    trigger = (
                        "CREATE CONSTRAINT TRIGGER reject_session_test "
                        "AFTER INSERT ON auth_sessions DEFERRABLE INITIALLY DEFERRED "
                        "FOR EACH ROW EXECUTE FUNCTION reject_session_test()"
                    )
                else:
                    action = (
                        "UPDATE"
                        if operation == "lookup"
                        else ("INSERT" if operation == "create" else "DELETE")
                    )
                    trigger = (
                        f"CREATE TRIGGER reject_session_test BEFORE {action} "
                        "ON auth_sessions "
                        "FOR EACH ROW EXECUTE FUNCTION reject_session_test()"
                    )
                await conn.execute(text(trigger))
            span_exporter.clear()
            log_exporter.clear()
            caplog.clear()
            with patch("learn_to_cloud.routes.auth_routes.oauth") as oauth:
                oauth.create_client.return_value = github
                if operation == "lookup":
                    response = await client.get("/api/user/me")
                elif operation in ("create", "commit"):
                    response = await client.get("/auth/callback")
                elif operation == "logout":
                    response = await client.post("/auth/logout")
                elif operation == "global":
                    response = await client.post(
                        "/auth/logout-all", data={"csrf": confirmation}
                    )
                else:
                    response = await client.delete("/api/user/me")
            assert response.status_code == 500
            assert "set-cookie" not in response.headers
            assert "location" not in response.headers
            assert client.cookies.get(AUTH_COOKIE_NAME) == token
            assert not {
                "auth.login.success",
                "auth.session.revoked",
                "user.account_deleted",
            } & {r.getMessage() for r in caplog.records}
            spans = span_exporter.get_finished_spans()
            assert any(
                span.kind == SpanKind.SERVER
                and span.status.status_code == StatusCode.ERROR
                for span in spans
            )
            assert any(span.kind == SpanKind.CLIENT for span in spans)
            telemetry = "\n".join(
                [span.to_json() for span in spans]
                + [record.to_json() for record in log_exporter.get_finished_logs()]
                + [_json_formatter().format(record) for record in caplog.records]
            )
            assert "unhandled.exception" in telemetry
            for prohibited in (
                token,
                digest.hex(),
                repr(digest),
                confirmation,
                "private-oauth-token",
                "private-session-username",
                test_settings.session.secret_key,
            ):
                assert prohibited not in telemetry
            async with engine.begin() as conn:
                await conn.execute(
                    text("DROP TRIGGER reject_session_test ON auth_sessions")
                )
                await conn.execute(text("DROP FUNCTION reject_session_test()"))
            assert (await client.get("/api/user/me")).status_code == 200
            async with app.state.session_maker() as db:
                assert await db.get(AuthSession, digest) is not None
                assert await db.get(User, 42) is not None
    finally:
        async with engine.begin() as conn:
            await conn.execute(
                text("DROP TRIGGER IF EXISTS reject_session_test ON auth_sessions")
            )
            await conn.execute(text("DROP FUNCTION IF EXISTS reject_session_test()"))
        FastAPIInstrumentor.uninstrument_app(app)
        instrumentor.uninstrument()
        root.removeHandler(handler)
        handler.close()
        log_provider.shutdown()
        trace_provider.shutdown()
        await engine.dispose()
