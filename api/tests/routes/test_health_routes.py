"""Unit tests for health check routes."""

from unittest.mock import MagicMock, patch

import pytest
from fastapi import HTTPException

from learn_to_cloud.routes.health_routes import health, ready


@pytest.mark.unit
class TestHealthEndpoint:
    """Tests for GET /health."""

    async def test_health_returns_200_healthy(self):
        """Health endpoint returns status=healthy."""
        result = await health()
        assert result.status == "healthy"
        assert result.service == "learn-to-cloud-api"


@pytest.mark.unit
class TestReadyEndpoint:
    """Tests for GET /ready."""

    async def test_ready_returns_200_when_healthy(self):
        """Ready returns 200 when init_done=True and DB is reachable."""
        request = MagicMock()
        request.app.state.init_error = None
        request.app.state.init_done = True
        request.app.state.alembic_code_head = None

        with patch(
            "learn_to_cloud.routes.health_routes.check_db_connection",
            autospec=True,
        ) as mock_check:
            result = await ready(request)

        assert result.status == "ready"
        assert result.service == "learn-to-cloud-api"
        mock_check.assert_awaited_once_with(
            request.app.state.engine,
            request.app.state.settings.database,
        )

    async def test_ready_returns_503_when_init_error(self):
        """Ready returns 503 when init_error is set."""
        request = MagicMock()
        request.app.state.init_error = "content load failed"
        request.app.state.init_done = False

        with pytest.raises(HTTPException) as exc_info:
            await ready(request)

        assert exc_info.value.status_code == 503
        assert "Initialization failed" in exc_info.value.detail

    async def test_ready_returns_503_when_init_not_done(self):
        """Ready returns 503 when background init hasn't finished."""
        request = MagicMock()
        request.app.state.init_error = None
        request.app.state.init_done = False

        with pytest.raises(HTTPException) as exc_info:
            await ready(request)

        assert exc_info.value.status_code == 503
        assert exc_info.value.detail == "Starting"

    async def test_ready_returns_503_when_db_check_fails(self):
        """Ready returns 503 when database connection check fails."""
        request = MagicMock()
        request.app.state.init_error = None
        request.app.state.init_done = True

        with (
            patch(
                "learn_to_cloud.routes.health_routes.check_db_connection",
                autospec=True,
                side_effect=ConnectionError("connection refused"),
            ),
            pytest.raises(HTTPException) as exc_info,
        ):
            await ready(request)

        assert exc_info.value.status_code == 503
        assert exc_info.value.detail == "Database unavailable"

    async def test_ready_logs_warning_on_schema_drift_but_still_200(self, caplog):
        """Ready logs a warning and still returns 200 when heads mismatch."""
        request = MagicMock()
        request.app.state.init_error = None
        request.app.state.init_done = True
        request.app.state.alembic_code_head = "code_head_abc"

        with (
            patch(
                "learn_to_cloud.routes.health_routes.check_db_connection",
                autospec=True,
            ),
            patch(
                "learn_to_cloud.routes.health_routes._get_db_alembic_head",
                autospec=True,
                return_value="db_head_xyz",
            ),
            caplog.at_level("WARNING"),
        ):
            result = await ready(request)

        assert result.status == "ready"
        assert "health.ready.schema_drift" in caplog.text

    async def test_ready_no_warning_when_heads_match(self, caplog):
        """Ready logs nothing extra when DB head matches code head."""
        request = MagicMock()
        request.app.state.init_error = None
        request.app.state.init_done = True
        request.app.state.alembic_code_head = "same_head"

        with (
            patch(
                "learn_to_cloud.routes.health_routes.check_db_connection",
                autospec=True,
            ),
            patch(
                "learn_to_cloud.routes.health_routes._get_db_alembic_head",
                autospec=True,
                return_value="same_head",
            ),
            caplog.at_level("WARNING"),
        ):
            result = await ready(request)

        assert result.status == "ready"
        assert "health.ready.schema_drift" not in caplog.text

    async def test_ready_returns_200_when_drift_check_itself_fails(self, caplog):
        """A broken drift check never turns into a 503 for /ready."""
        request = MagicMock()
        request.app.state.init_error = None
        request.app.state.init_done = True
        request.app.state.alembic_code_head = "code_head_abc"

        with (
            patch(
                "learn_to_cloud.routes.health_routes.check_db_connection",
                autospec=True,
            ),
            patch(
                "learn_to_cloud.routes.health_routes._get_db_alembic_head",
                autospec=True,
                side_effect=RuntimeError("alembic_version table missing"),
            ),
            caplog.at_level("WARNING"),
        ):
            result = await ready(request)

        assert result.status == "ready"
        assert "health.ready.schema_drift_check_failed" in caplog.text

    async def test_ready_skips_drift_check_when_code_head_unknown(self):
        """No drift check runs if the code head couldn't be resolved at startup."""
        request = MagicMock()
        request.app.state.init_error = None
        request.app.state.init_done = True
        request.app.state.alembic_code_head = None

        with (
            patch(
                "learn_to_cloud.routes.health_routes.check_db_connection",
                autospec=True,
            ),
            patch(
                "learn_to_cloud.routes.health_routes._get_db_alembic_head",
                autospec=True,
            ) as mock_db_head,
        ):
            result = await ready(request)

        assert result.status == "ready"
        mock_db_head.assert_not_called()


@pytest.mark.unit
class TestGetCodeAlembicHead:
    """Tests for get_code_alembic_head()."""

    def test_returns_head_revision_from_script_directory(self):
        """Resolves the real head from the repo's alembic/ script directory."""
        from learn_to_cloud.routes.health_routes import get_code_alembic_head

        head = get_code_alembic_head()
        assert head is not None
        assert isinstance(head, str)

    def test_returns_none_when_script_directory_resolution_fails(self):
        """Returns None instead of raising if Config/ScriptDirectory blow up."""
        from learn_to_cloud.routes import health_routes

        with patch.object(
            health_routes.ScriptDirectory,
            "from_config",
            side_effect=RuntimeError("boom"),
        ):
            assert health_routes.get_code_alembic_head() is None
