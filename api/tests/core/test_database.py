"""Tests for core database module."""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlalchemy.ext.asyncio import AsyncEngine
from sqlalchemy.pool import QueuePool

from core.database import (
    PoolStatus,
    _build_azure_database_url,
    _get_azure_credential,
    _get_azure_token,
    _get_azure_token_sync,
    _reset_azure_credential,
    check_azure_token_acquisition,
    check_db_connection,
    comprehensive_health_check,
    create_engine,
    create_session_maker,
    dispose_engine,
    get_pool_status,
    init_db,
    reset_azure_credential,
)

pytestmark = pytest.mark.unit


class TestPoolStatus:
    """Tests for PoolStatus named tuple."""

    def test_creates_named_tuple(self):
        """Test creates PoolStatus with all fields."""
        status = PoolStatus(pool_size=5, checked_out=2, overflow=1, checked_in=3)

        assert status.pool_size == 5
        assert status.checked_out == 2
        assert status.overflow == 1
        assert status.checked_in == 3


class TestAzureCredential:
    """Tests for Azure credential functions."""

    def test_get_azure_credential_creates_new(self):
        """Test creates new DefaultAzureCredential."""
        _reset_azure_credential()

        with patch("azure.identity.DefaultAzureCredential") as mock_cred_class:
            mock_cred = MagicMock()
            mock_cred_class.return_value = mock_cred

            credential = _get_azure_credential()

            assert credential is mock_cred
            mock_cred_class.assert_called_once()

        _reset_azure_credential()

    def test_get_azure_credential_reuses_existing(self):
        """Test reuses existing credential."""
        _reset_azure_credential()

        with patch("azure.identity.DefaultAzureCredential") as mock_cred_class:
            mock_cred = MagicMock()
            mock_cred_class.return_value = mock_cred

            cred1 = _get_azure_credential()
            cred2 = _get_azure_credential()

            assert cred1 is cred2
            assert mock_cred_class.call_count == 1

        _reset_azure_credential()

    def test_reset_azure_credential_clears_cache(self):
        """Test reset clears the cached credential."""
        import core.database as db_module

        # Inject mock for testing reset behavior (use setattr to bypass type check)
        setattr(db_module, "_azure_credential", MagicMock())

        reset_azure_credential()

        assert db_module._azure_credential is None


class TestGetAzureTokenSync:
    """Tests for _get_azure_token_sync function."""

    def test_gets_token_from_credential(self):
        """Test gets token using credential."""
        _reset_azure_credential()

        mock_token = MagicMock()
        mock_token.token = "test-azure-token"

        with patch("azure.identity.DefaultAzureCredential") as mock_cred_class:
            mock_cred = MagicMock()
            mock_cred.get_token.return_value = mock_token
            mock_cred_class.return_value = mock_cred

            token = _get_azure_token_sync()

            assert token == "test-azure-token"
            mock_cred.get_token.assert_called_once()

        _reset_azure_credential()


class TestGetAzureToken:
    """Tests for _get_azure_token async function."""

    @pytest.mark.asyncio
    async def test_returns_token(self):
        """Test returns token from sync function."""
        with patch("core.database._get_azure_token_sync", return_value="async-token"):
            token = await _get_azure_token()
            assert token == "async-token"

    @pytest.mark.asyncio
    async def test_resets_credential_on_timeout(self):
        """Test resets credential cache on timeout - uses real retry logic."""
        # Note: The _get_azure_token function has tenacity retry that calls
        # _reset_azure_credential before each retry. This test verifies the
        # timeout behavior without mocking the reset function.
        _reset_azure_credential()

        with patch("core.database.asyncio.to_thread", side_effect=asyncio.TimeoutError):
            with pytest.raises(TimeoutError):
                await _get_azure_token()


class TestBuildAzureDatabaseUrl:
    """Tests for _build_azure_database_url function."""

    def test_builds_url_with_settings(self):
        """Test builds correct connection URL."""
        with patch("core.database.get_settings") as mock_settings:
            mock_settings.return_value.postgres_user = "admin@server"
            mock_settings.return_value.postgres_host = (
                "server.postgres.database.azure.com"
            )
            mock_settings.return_value.postgres_database = "mydb"

            url = _build_azure_database_url()

            assert "postgresql+asyncpg://" in url
            assert "admin@server" in url
            assert "server.postgres.database.azure.com" in url
            assert "mydb" in url
            assert "ssl=require" in url


class TestCreateEngine:
    """Tests for create_engine function."""

    def test_creates_engine_for_local_postgres(self):
        """Test creates engine for local PostgreSQL."""
        with patch("core.database.get_settings") as mock_settings:
            mock_settings.return_value.use_azure_postgres = False
            mock_settings.return_value.database_url = (
                "postgresql+asyncpg://user:pass@localhost/db"
            )
            mock_settings.return_value.db_echo = False
            mock_settings.return_value.db_pool_size = 5
            mock_settings.return_value.db_pool_max_overflow = 10
            mock_settings.return_value.db_pool_timeout = 30
            mock_settings.return_value.db_pool_recycle = 1800
            mock_settings.return_value.db_statement_timeout_ms = 30000

            with patch("core.database.create_async_engine") as mock_create:
                with patch("core.database._setup_pool_event_listeners"):
                    mock_engine = MagicMock()
                    mock_create.return_value = mock_engine

                    engine = create_engine()

                    assert engine is mock_engine
                    mock_create.assert_called_once()

    def test_creates_engine_for_azure_postgres(self):
        """Test creates engine for Azure PostgreSQL with managed identity."""
        with patch("core.database.get_settings") as mock_settings:
            mock_settings.return_value.use_azure_postgres = True
            mock_settings.return_value.postgres_user = "admin"
            mock_settings.return_value.postgres_host = (
                "server.postgres.database.azure.com"
            )
            mock_settings.return_value.postgres_database = "mydb"
            mock_settings.return_value.db_echo = False
            mock_settings.return_value.db_pool_size = 5
            mock_settings.return_value.db_pool_max_overflow = 10
            mock_settings.return_value.db_pool_timeout = 30
            mock_settings.return_value.db_pool_recycle = 1800

            with patch("core.database.create_async_engine") as mock_create:
                with patch("core.database._setup_pool_event_listeners"):
                    mock_engine = MagicMock()
                    mock_create.return_value = mock_engine

                    create_engine()

                    # Check async_creator is passed for Azure
                    call_kwargs = mock_create.call_args[1]
                    assert "async_creator" in call_kwargs


class TestCreateSessionMaker:
    """Tests for create_session_maker function."""

    def test_creates_session_maker(self):
        """Test creates async session maker."""
        mock_engine = MagicMock(spec=AsyncEngine)

        session_maker = create_session_maker(mock_engine)

        assert session_maker is not None


class TestInitDb:
    """Tests for init_db function."""

    @pytest.mark.asyncio
    async def test_verifies_database_connectivity(self):
        """Test verifies database is reachable."""
        mock_engine = MagicMock(spec=AsyncEngine)
        mock_conn = AsyncMock()
        mock_conn.execute = AsyncMock()

        mock_engine.connect = MagicMock(
            return_value=AsyncMock(
                __aenter__=AsyncMock(return_value=mock_conn), __aexit__=AsyncMock()
            )
        )

        await init_db(mock_engine)

        # Connection should have been used
        mock_engine.connect.assert_called()

    @pytest.mark.asyncio
    async def test_raises_on_connection_failure(self):
        """Test raises on database connection failure."""
        mock_engine = MagicMock(spec=AsyncEngine)
        mock_engine.connect.side_effect = Exception("Connection refused")

        with pytest.raises(Exception, match="Connection refused"):
            await init_db(mock_engine)


class TestDisposeEngine:
    """Tests for dispose_engine function."""

    @pytest.mark.asyncio
    async def test_disposes_engine(self):
        """Test disposes the engine."""
        mock_engine = MagicMock(spec=AsyncEngine)
        mock_engine.dispose = AsyncMock()

        await dispose_engine(mock_engine)

        mock_engine.dispose.assert_called_once()


class TestCheckDbConnection:
    """Tests for check_db_connection function."""

    @pytest.mark.asyncio
    async def test_executes_select_1(self):
        """Test executes SELECT 1 query."""
        mock_engine = MagicMock(spec=AsyncEngine)
        mock_conn = AsyncMock()
        mock_conn.execute = AsyncMock()

        async def mock_connect():
            return mock_conn

        mock_engine.connect = MagicMock(
            return_value=AsyncMock(
                __aenter__=AsyncMock(return_value=mock_conn),
                __aexit__=AsyncMock(),
            )
        )

        await check_db_connection(mock_engine)

        mock_conn.execute.assert_called_once()


class TestGetPoolStatus:
    """Tests for get_pool_status function."""

    def test_returns_pool_status_for_queue_pool(self):
        """Test returns PoolStatus for QueuePool."""
        mock_engine = MagicMock(spec=AsyncEngine)
        mock_pool = MagicMock(spec=QueuePool)
        mock_pool.size.return_value = 5
        mock_pool.checkedout.return_value = 2
        mock_pool.overflow.return_value = 1
        mock_pool.checkedin.return_value = 3
        mock_engine.sync_engine.pool = mock_pool

        status = get_pool_status(mock_engine)

        assert status is not None
        assert status.pool_size == 5
        assert status.checked_out == 2
        assert status.overflow == 1
        assert status.checked_in == 3

    def test_returns_none_for_non_queue_pool(self):
        """Test returns None for non-QueuePool."""
        mock_engine = MagicMock(spec=AsyncEngine)
        mock_engine.sync_engine.pool = MagicMock()  # Not a QueuePool

        status = get_pool_status(mock_engine)

        assert status is None


class TestCheckAzureTokenAcquisition:
    """Tests for check_azure_token_acquisition function."""

    @pytest.mark.asyncio
    async def test_returns_true_when_not_using_azure(self):
        """Test returns True when not using Azure auth."""
        with patch("core.database.get_settings") as mock_settings:
            mock_settings.return_value.use_azure_postgres = False

            result = await check_azure_token_acquisition()

            assert result is True

    @pytest.mark.asyncio
    async def test_acquires_token_when_using_azure(self):
        """Test acquires token when using Azure auth."""
        with patch("core.database.get_settings") as mock_settings:
            mock_settings.return_value.use_azure_postgres = True

            with patch("core.database._get_azure_token", return_value="test-token"):
                result = await check_azure_token_acquisition()

                assert result is True


class TestComprehensiveHealthCheck:
    """Tests for comprehensive_health_check function."""

    @pytest.mark.asyncio
    async def test_returns_health_status(self):
        """Test returns comprehensive health status."""
        mock_engine = MagicMock(spec=AsyncEngine)

        with patch("core.database.get_settings") as mock_settings:
            mock_settings.return_value.use_azure_postgres = False

            with patch("core.database.check_db_connection", new_callable=AsyncMock):
                with patch("core.database.get_pool_status", return_value=None):
                    result = await comprehensive_health_check(mock_engine)

                    assert "database" in result
                    assert "azure_auth" in result
                    assert "pool" in result
                    assert result["database"] is True

    @pytest.mark.asyncio
    async def test_handles_database_failure(self):
        """Test handles database connection failure."""
        mock_engine = MagicMock(spec=AsyncEngine)

        with patch("core.database.get_settings") as mock_settings:
            mock_settings.return_value.use_azure_postgres = False

            with patch(
                "core.database.check_db_connection",
                side_effect=Exception("DB error"),
            ):
                with patch("core.database.get_pool_status", return_value=None):
                    result = await comprehensive_health_check(mock_engine)

                    assert result["database"] is False

    @pytest.mark.asyncio
    async def test_checks_azure_auth_when_enabled(self):
        """Test checks Azure auth when using Azure PostgreSQL."""
        mock_engine = MagicMock(spec=AsyncEngine)

        with patch("core.database.get_settings") as mock_settings:
            mock_settings.return_value.use_azure_postgres = True

            with patch(
                "core.database.check_azure_token_acquisition",
                new_callable=AsyncMock,
                return_value=True,
            ):
                with patch("core.database.check_db_connection", new_callable=AsyncMock):
                    with patch("core.database.get_pool_status", return_value=None):
                        result = await comprehensive_health_check(mock_engine)

                        assert result["azure_auth"] is True

    @pytest.mark.asyncio
    async def test_skips_db_check_on_azure_auth_failure(self):
        """Test skips DB check when Azure auth fails."""
        mock_engine = MagicMock(spec=AsyncEngine)

        with patch("core.database.get_settings") as mock_settings:
            mock_settings.return_value.use_azure_postgres = True

            with patch(
                "core.database.check_azure_token_acquisition",
                side_effect=Exception("Auth failed"),
            ):
                result = await comprehensive_health_check(mock_engine)

                assert result["azure_auth"] is False
                assert result["database"] is False
