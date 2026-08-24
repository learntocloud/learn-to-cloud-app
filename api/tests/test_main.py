"""Unit tests for the FastAPI app's startup lifespan.

Covers the curriculum artifact fail-fast contract: a missing/corrupted
packaged artifact must abort application startup (not merely mark
``/ready`` unhealthy), and a successful load must be recorded on
``app.state`` and logged for telemetry.
"""

from __future__ import annotations

import ast
import inspect
import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from learn_to_cloud_shared.content_catalog import CurriculumCatalogError
from slowapi.errors import RateLimitExceeded

from learn_to_cloud import main as main_module
from learn_to_cloud.core.ratelimit import rate_limit_exceeded_handler
from learn_to_cloud.main import (
    app,
    global_exception_handler,
    lifespan,
    validation_exception_handler,
)

pytestmark = pytest.mark.unit


def _fake_catalog(
    *, curriculum_version: int = 7, artifact_schema_version: int = 1
) -> MagicMock:
    catalog = MagicMock()
    catalog.curriculum_version = curriculum_version
    catalog.artifact_schema_version = artifact_schema_version
    catalog.content_hash = "deadbeef"
    return catalog


def _request(path: str = "/api/test", method: str = "GET") -> Request:
    return Request(
        {
            "type": "http",
            "method": method,
            "path": path,
            "headers": [],
            "query_string": b"",
            "server": ("testserver", 80),
            "client": ("testclient", 50000),
            "scheme": "http",
        }
    )


@pytest.fixture
def fake_app() -> FastAPI:
    return FastAPI()


@pytest.fixture(autouse=True)
def _patch_startup_dependencies(test_settings):
    """Patch every I/O dependency lifespan touches, except the curriculum catalog."""
    with (
        patch("learn_to_cloud.main.get_web_settings", return_value=test_settings),
        patch("learn_to_cloud.main.create_engine", return_value=MagicMock()),
        patch("learn_to_cloud.main.create_session_maker", return_value=MagicMock()),
        patch("learn_to_cloud.main.get_code_alembic_head", return_value="head123"),
        patch("learn_to_cloud.main.init_oauth"),
        patch("learn_to_cloud.main.init_db", new=AsyncMock()),
        patch("learn_to_cloud.main.close_github_client", new=AsyncMock()),
        patch("learn_to_cloud.main.dispose_engine", new=AsyncMock()),
    ):
        yield


def test_observability_fails_fast_before_fastapi_construction():
    tree = ast.parse(inspect.getsource(main_module))
    configure_call: ast.Call | None = None
    app_assignment_line: int | None = None
    for node in tree.body:
        if (
            isinstance(node, ast.Expr)
            and isinstance(node.value, ast.Call)
            and isinstance(node.value.func, ast.Name)
            and node.value.func.id == "configure_observability"
        ):
            configure_call = node.value
        elif isinstance(node, ast.Assign) and any(
            isinstance(target, ast.Name) and target.id == "app"
            for target in node.targets
        ):
            app_assignment_line = node.lineno

    assert configure_call is not None
    assert app_assignment_line is not None
    assert configure_call.lineno < app_assignment_line
    assert len(configure_call.keywords) == 1
    keyword = configure_call.keywords[0]
    assert keyword.arg == "fail_on_azure_error"
    assert isinstance(keyword.value, ast.Constant)
    assert keyword.value.value is True


def test_exception_handlers_are_registered_for_their_dispatch_types():
    assert app.exception_handlers[RateLimitExceeded] is rate_limit_exceeded_handler
    assert (
        app.exception_handlers[RequestValidationError] is validation_exception_handler
    )
    assert app.exception_handlers[Exception] is global_exception_handler


@pytest.mark.asyncio
async def test_global_exception_handler_logs_once_and_returns_500(
    caplog: pytest.LogCaptureFixture,
):
    request = _request(path="/api/crash", method="POST")

    with caplog.at_level("ERROR", logger="learn_to_cloud.main"):
        try:
            raise RuntimeError("boom")
        except RuntimeError as exc:
            response = await global_exception_handler(request, exc)

    assert response.status_code == 500
    assert json.loads(bytes(response.body)) == {
        "detail": "An unexpected error occurred. Please try again."
    }
    records = [
        record for record in caplog.records if record.message == "unhandled.exception"
    ]
    assert len(records) == 1
    record = records[0]
    assert record.exc_info is not None
    assert record.__dict__["exc_type"] == "RuntimeError"
    assert record.__dict__["path"] == "/api/crash"
    assert record.__dict__["method"] == "POST"


@pytest.mark.asyncio
async def test_validation_exception_handler_preserves_422_response():
    exc = RequestValidationError(
        [
            {
                "type": "missing",
                "loc": ("body", "name"),
                "msg": "Field required",
                "input": {},
            }
        ]
    )

    response = await validation_exception_handler(
        _request(path="/api/users", method="POST"),
        exc,
    )

    assert response.status_code == 422
    assert json.loads(bytes(response.body))["detail"] == [
        {
            "type": "missing",
            "loc": ["body", "name"],
            "msg": "Field required",
            "input": {},
        }
    ]


@pytest.mark.asyncio
class TestLifespanCurriculumFailFast:
    async def test_catalog_load_failure_aborts_startup(self, fake_app: FastAPI):
        """A broken/missing artifact must prevent the app from starting."""
        with (
            patch(
                "learn_to_cloud.main.get_curriculum_catalog",
                side_effect=CurriculumCatalogError("artifact missing"),
            ),
            pytest.raises(CurriculumCatalogError, match="artifact missing"),
        ):
            async with lifespan(fake_app):
                pytest.fail("lifespan must not yield when the catalog fails to load")

    async def test_successful_load_is_recorded_and_logged(
        self, fake_app: FastAPI, caplog: pytest.LogCaptureFixture
    ):
        catalog = _fake_catalog(curriculum_version=3)

        with (
            patch("learn_to_cloud.main.get_curriculum_catalog", return_value=catalog),
            caplog.at_level("INFO"),
        ):
            async with lifespan(fake_app):
                assert fake_app.state.curriculum_catalog is catalog

        assert "init.curriculum_loaded" in caplog.text
