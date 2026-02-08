"""Tests for core.database module.

Covers the module-specific logic that isn't exercised by integration tests:
- Azure credential locking and reset
- Azure token retry/timeout behavior
- Pool checkout event (transaction state cleanup + safety net)
- Health check timeout behavior
- get_db / get_db_readonly commit/rollback semantics
"""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
async def _reset_credential():
    """Reset the module-level credential cache before each test."""
    import core.azure_auth as auth_mod

    async with auth_mod._credential_lock:
        auth_mod._azure_credential = None
    yield
    async with auth_mod._credential_lock:
        auth_mod._azure_credential = None


# ===========================================================================
# Azure credential locking
# ===========================================================================


class TestAzureCredentialLocking:
    """Verify get_credential uses asyncio.Lock correctly."""

    @patch("azure.identity.DefaultAzureCredential")
    async def test_single_credential_created_on_concurrent_calls(
        self, mock_cred_cls: MagicMock
    ):
        """Concurrent calls should create only one DefaultAzureCredential."""
        from core.azure_auth import get_credential

        sentinel = MagicMock(name="credential_instance")
        mock_cred_cls.return_value = sentinel

        results = await asyncio.gather(
            get_credential(),
            get_credential(),
            get_credential(),
        )

        # All three should return the same instance
        assert all(r is sentinel for r in results)
        mock_cred_cls.assert_called_once()

    async def test_reset_clears_credential(self):
        """reset_credential should set the cache to None."""
        import core.azure_auth as auth_mod
        from core.azure_auth import get_credential, reset_credential

        with patch(
            "azure.identity.DefaultAzureCredential",
            return_value=MagicMock(),
        ):
            await get_credential()
            assert auth_mod._azure_credential is not None

        await reset_credential()

        async with auth_mod._credential_lock:
            assert auth_mod._azure_credential is None


# ===========================================================================
# Azure token retry / timeout
# ===========================================================================


class TestAzureTokenRetryTimeout:
    """Verify get_token retry and timeout behavior."""

    async def test_timeout_resets_credential(self):
        """When token acquisition times out, credential should be reset."""
        import core.azure_auth as auth_mod

        fake_credential = MagicMock()

        # get_token blocks forever → triggers timeout
        async def hang_forever(*args, **kwargs):
            await asyncio.sleep(9999)

        with (
            patch(
                "azure.identity.DefaultAzureCredential",
                return_value=fake_credential,
            ),
            patch.object(auth_mod, "AZURE_TOKEN_TIMEOUT", 0.05),
            patch.object(auth_mod, "_AZURE_RETRY_ATTEMPTS", 1),
            patch("asyncio.to_thread", side_effect=hang_forever),
        ):
            # We call the inner logic directly via __wrapped__ to bypass tenacity
            with pytest.raises(TimeoutError):
                await auth_mod.get_token.__wrapped__()  # type: ignore[attr-defined]

        # Credential should have been reset
        async with auth_mod._credential_lock:
            assert auth_mod._azure_credential is None

    async def test_successful_token_acquisition(self):
        """Happy path: token acquired successfully."""
        import core.azure_auth as auth_mod

        fake_credential = MagicMock()
        fake_token = MagicMock()
        fake_token.token = "test-token-123"
        fake_credential.get_token.return_value = fake_token

        with patch(
            "azure.identity.DefaultAzureCredential",
            return_value=fake_credential,
        ):
            token = await auth_mod.get_token.__wrapped__()  # type: ignore[attr-defined]

        assert token == "test-token-123"
        fake_credential.get_token.assert_called_once()


# ===========================================================================
# Pool checkout event — transaction state cleanup
# ===========================================================================


class TestCheckoutEventTransactionCleanup:
    """Verify the pool checkout event handles asyncpg transaction state."""

    def _make_mock_dbapi_conn(self, *, in_transaction: bool = True):
        """Create a mock that mimics SQLAlchemy's asyncpg AdaptedConnection."""
        raw_conn = MagicMock(name="raw_asyncpg_connection")
        raw_conn.is_in_transaction.return_value = in_transaction

        dbapi_conn = MagicMock(name="adapted_connection")
        dbapi_conn._connection = raw_conn
        dbapi_conn._transaction = MagicMock()
        dbapi_conn._started = True
        return dbapi_conn, raw_conn

    def test_rollback_and_reset_when_in_transaction(self):
        """Checkout should ROLLBACK and reset adapter state."""
        from core.database import _setup_pool_event_listeners

        # Build a mock engine just to capture the checkout listener
        mock_pool = MagicMock()
        mock_engine = MagicMock()
        mock_engine.sync_engine.pool = mock_pool

        # Capture the checkout listener
        listeners: dict = {}

        def fake_listens_for(target, event_name):
            def decorator(fn):
                listeners[event_name] = fn
                return fn

            return decorator

        with patch("core.database.event.listens_for", side_effect=fake_listens_for):
            _setup_pool_event_listeners(mock_engine)

        checkout_fn = listeners["checkout"]
        dbapi_conn, raw_conn = self._make_mock_dbapi_conn(in_transaction=True)

        checkout_fn(dbapi_conn, MagicMock(), MagicMock())

        # Should have executed ROLLBACK
        dbapi_conn.await_.assert_called_once_with(raw_conn.execute("ROLLBACK"))
        # Adapter state should be reset
        assert dbapi_conn._transaction is None
        assert dbapi_conn._started is False

    def test_no_rollback_when_not_in_transaction(self):
        """Checkout should skip ROLLBACK if no active transaction."""
        from core.database import _setup_pool_event_listeners

        mock_pool = MagicMock()
        mock_engine = MagicMock()
        mock_engine.sync_engine.pool = mock_pool

        listeners: dict = {}

        def fake_listens_for(target, event_name):
            def decorator(fn):
                listeners[event_name] = fn
                return fn

            return decorator

        with patch("core.database.event.listens_for", side_effect=fake_listens_for):
            _setup_pool_event_listeners(mock_engine)

        checkout_fn = listeners["checkout"]
        dbapi_conn, _raw_conn = self._make_mock_dbapi_conn(in_transaction=False)

        checkout_fn(dbapi_conn, MagicMock(), MagicMock())

        # Should NOT have called await_ (no ROLLBACK needed)
        dbapi_conn.await_.assert_not_called()

    def test_safety_net_on_missing_private_attrs(self):
        """If _transaction/_started are missing, should not crash."""
        from core.database import _setup_pool_event_listeners

        mock_pool = MagicMock()
        mock_engine = MagicMock()
        mock_engine.sync_engine.pool = mock_pool

        listeners: dict = {}

        def fake_listens_for(target, event_name):
            def decorator(fn):
                listeners[event_name] = fn
                return fn

            return decorator

        with patch("core.database.event.listens_for", side_effect=fake_listens_for):
            _setup_pool_event_listeners(mock_engine)

        checkout_fn = listeners["checkout"]

        # Create a dbapi_conn where setting _transaction raises AttributeError
        raw_conn = MagicMock()
        raw_conn.is_in_transaction.return_value = True
        dbapi_conn = MagicMock()
        dbapi_conn._connection = raw_conn

        # Make _transaction assignment raise AttributeError
        type(dbapi_conn)._transaction = property(
            fget=lambda self: None,
            fset=MagicMock(side_effect=AttributeError("no such attr")),
        )

        # Should NOT raise — safety net catches AttributeError
        checkout_fn(dbapi_conn, MagicMock(), MagicMock())

        # ROLLBACK should still have been attempted
        dbapi_conn.await_.assert_called_once()


# ===========================================================================
# Health check timeout
# ===========================================================================


class TestCheckDbConnection:
    """Verify check_db_connection has a timeout guard."""

    async def test_timeout_on_hanging_connection(self):
        """check_db_connection should raise TimeoutError if DB hangs."""
        from core.database import check_db_connection

        # Make engine.connect().__aenter__ hang
        async def hang_forever(*_args, **_kwargs):
            await asyncio.sleep(9999)

        mock_conn = AsyncMock()
        mock_conn.execute = AsyncMock(side_effect=hang_forever)

        # engine.connect() returns an async CM (sync call, not coroutine)
        mock_cm = AsyncMock()
        mock_cm.__aenter__ = AsyncMock(return_value=mock_conn)
        mock_cm.__aexit__ = AsyncMock(return_value=False)

        mock_engine = AsyncMock()
        mock_engine.connect = MagicMock(return_value=mock_cm)

        # Capture the real asyncio.timeout before patching to avoid recursion
        real_timeout = asyncio.timeout

        # Replace the 30s timeout with 0.05s for test speed
        with (
            patch(
                "core.database.asyncio.timeout",
                side_effect=lambda _: real_timeout(0.05),
            ),
            pytest.raises(TimeoutError),
        ):
            await check_db_connection(mock_engine)

    async def test_success_path(self):
        """check_db_connection should succeed when DB responds."""
        from core.database import check_db_connection

        mock_conn = AsyncMock()
        mock_cm = AsyncMock()
        mock_cm.__aenter__ = AsyncMock(return_value=mock_conn)
        mock_cm.__aexit__ = AsyncMock(return_value=False)

        mock_engine = AsyncMock()
        # connect() is a sync call returning an async CM
        mock_engine.connect = MagicMock(return_value=mock_cm)

        # Should not raise
        await check_db_connection(mock_engine)

        mock_conn.execute.assert_awaited_once()
        mock_conn.rollback.assert_awaited_once()


# ===========================================================================
# get_db / get_db_readonly commit / rollback
# ===========================================================================


class TestGetDbDependency:
    """Verify get_db commits on success and rolls back on failure."""

    def _make_mock_request(self):
        """Create a mock Request with app.state.session_maker."""
        mock_session = AsyncMock(
            spec_set=["commit", "rollback", "__aenter__", "__aexit__"],
        )
        mock_session.commit = AsyncMock()
        mock_session.rollback = AsyncMock()
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=False)

        mock_session_maker = MagicMock()
        mock_session_maker.return_value = mock_session

        mock_request = MagicMock()
        mock_request.app.state.session_maker = mock_session_maker

        return mock_request, mock_session

    async def test_commit_on_success(self):
        """get_db should commit when no exception occurs."""
        from core.database import get_db

        mock_request, mock_session = self._make_mock_request()

        gen = get_db(mock_request)
        session = await gen.__anext__()
        assert session is mock_session

        # Simulate successful completion (StopAsyncIteration)
        with pytest.raises(StopAsyncIteration):
            await gen.__anext__()

        mock_session.commit.assert_awaited_once()
        mock_session.rollback.assert_not_awaited()

    async def test_rollback_on_exception(self):
        """get_db should rollback when an exception is thrown into the generator."""
        from core.database import get_db

        mock_request, mock_session = self._make_mock_request()

        gen = get_db(mock_request)
        await gen.__anext__()

        # Throw an exception into the generator
        with pytest.raises(ValueError, match="test error"):
            await gen.athrow(ValueError("test error"))

        mock_session.rollback.assert_awaited_once()
        mock_session.commit.assert_not_awaited()

    async def test_rollback_failure_does_not_mask_original_error(self):
        """If rollback fails, the original exception should still propagate."""
        from core.database import get_db

        mock_request, mock_session = self._make_mock_request()
        mock_session.rollback = AsyncMock(side_effect=RuntimeError("rollback failed"))

        gen = get_db(mock_request)
        await gen.__anext__()

        # The original ValueError should propagate, not the rollback error
        with pytest.raises(ValueError, match="original"):
            await gen.athrow(ValueError("original"))


class TestGetDbReadonlyDependency:
    """Verify get_db_readonly does NOT commit."""

    def _make_mock_request(self):
        mock_session = AsyncMock(
            spec_set=["commit", "rollback", "__aenter__", "__aexit__"],
        )
        mock_session.commit = AsyncMock()
        mock_session.rollback = AsyncMock()
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=False)

        mock_session_maker = MagicMock()
        mock_session_maker.return_value = mock_session

        mock_request = MagicMock()
        mock_request.app.state.session_maker = mock_session_maker

        return mock_request, mock_session

    async def test_no_commit_on_success(self):
        """get_db_readonly should NOT call commit."""
        from core.database import get_db_readonly

        mock_request, mock_session = self._make_mock_request()

        gen = get_db_readonly(mock_request)
        session = await gen.__anext__()
        assert session is mock_session

        with pytest.raises(StopAsyncIteration):
            await gen.__anext__()

        mock_session.commit.assert_not_awaited()
        mock_session.rollback.assert_not_awaited()

    async def test_rollback_on_exception(self):
        """get_db_readonly should rollback on exception."""
        from core.database import get_db_readonly

        mock_request, mock_session = self._make_mock_request()

        gen = get_db_readonly(mock_request)
        await gen.__anext__()

        with pytest.raises(ValueError):
            await gen.athrow(ValueError("boom"))

        mock_session.rollback.assert_awaited_once()
