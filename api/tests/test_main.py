"""Unit tests for the FastAPI app's startup lifespan.

Covers the curriculum artifact fail-fast contract: a missing/corrupted
packaged artifact must abort application startup (not merely mark
``/ready`` unhealthy), and a successful load must be recorded on
``app.state`` and logged for telemetry.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI
from learn_to_cloud_shared.content_catalog import CurriculumCatalogError

from learn_to_cloud.main import lifespan

pytestmark = pytest.mark.unit


def _fake_catalog(
    *, curriculum_version: int = 7, artifact_schema_version: int = 1
) -> MagicMock:
    catalog = MagicMock()
    catalog.curriculum_version = curriculum_version
    catalog.artifact_schema_version = artifact_schema_version
    catalog.content_hash = "deadbeef"
    return catalog


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
