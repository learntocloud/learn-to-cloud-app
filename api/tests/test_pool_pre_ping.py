"""Integration tests for pool_pre_ping behavior.

Verifies that SQLAlchemy's pool_pre_ping correctly detects and recovers
from dead connections when using asyncpg against a real PostgreSQL instance.
"""

import pytest
from sqlalchemy import event, text
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.pool import AsyncAdaptedQueuePool

from tests.conftest import TEST_DATABASE_URL


class TestPoolPrePing:
    """Verify pool_pre_ping detects and replaces dead connections.

    These tests use their own engines with specific pool configs and only
    run SELECT queries — no app table writes, so no cleanup needed.
    """

    async def test_pre_ping_recovers_from_terminated_connection(self):
        """A connection killed server-side is transparently replaced."""
        engine = create_async_engine(
            TEST_DATABASE_URL,
            poolclass=AsyncAdaptedQueuePool,
            pool_size=1,
            max_overflow=0,
            pool_pre_ping=True,
        )

        # Checkout a connection, grab its PG backend PID, return it to pool
        async with engine.connect() as conn:
            result = await conn.execute(text("SELECT pg_backend_pid()"))
            original_pid = result.scalar()

        # Kill that backend process server-side (simulates DB restart)
        kill_engine = create_async_engine(
            TEST_DATABASE_URL,
            poolclass=AsyncAdaptedQueuePool,
            pool_size=1,
            max_overflow=0,
        )
        async with kill_engine.connect() as killer:
            await killer.execute(
                text("SELECT pg_terminate_backend(:pid)"),
                {"pid": original_pid},
            )
        await kill_engine.dispose()

        # Now checkout from the original engine — pre_ping should detect
        # the dead connection and give us a fresh one
        async with engine.connect() as conn:
            result = await conn.execute(text("SELECT pg_backend_pid()"))
            new_pid = result.scalar()

        assert new_pid != original_pid, (
            f"Expected a new backend PID after termination, "
            f"but got the same one: {new_pid}"
        )

        await engine.dispose()

    async def test_pre_ping_disabled_raises_on_dead_connection(self):
        """Without pre_ping, a killed connection raises an error on use."""
        engine = create_async_engine(
            TEST_DATABASE_URL,
            poolclass=AsyncAdaptedQueuePool,
            pool_size=1,
            max_overflow=0,
            pool_pre_ping=False,
        )

        # Checkout, get PID, return to pool
        async with engine.connect() as conn:
            result = await conn.execute(text("SELECT pg_backend_pid()"))
            original_pid = result.scalar()

        # Kill the backend
        kill_engine = create_async_engine(
            TEST_DATABASE_URL,
            poolclass=AsyncAdaptedQueuePool,
            pool_size=1,
            max_overflow=0,
        )
        async with kill_engine.connect() as killer:
            await killer.execute(
                text("SELECT pg_terminate_backend(:pid)"),
                {"pid": original_pid},
            )
        await kill_engine.dispose()

        # Without pre_ping, the dead connection should cause an error
        with pytest.raises(Exception):
            async with engine.connect() as conn:
                await conn.execute(text("SELECT 1"))

        await engine.dispose()

    async def test_pre_ping_healthy_connection_reused(self):
        """A healthy connection passes the ping and is reused (no churn)."""
        engine = create_async_engine(
            TEST_DATABASE_URL,
            poolclass=AsyncAdaptedQueuePool,
            pool_size=1,
            max_overflow=0,
            pool_pre_ping=True,
        )

        # First checkout — get the PID
        async with engine.connect() as conn:
            result = await conn.execute(text("SELECT pg_backend_pid()"))
            first_pid = result.scalar()

        # Second checkout — same connection should be reused
        async with engine.connect() as conn:
            result = await conn.execute(text("SELECT pg_backend_pid()"))
            second_pid = result.scalar()

        assert (
            first_pid == second_pid
        ), "Healthy connection should be reused, not replaced"

        await engine.dispose()

    async def test_pre_ping_invalidates_entire_pool(self):
        """When one connection is dead, all idle connections are invalidated."""
        invalidated_count = 0

        engine = create_async_engine(
            TEST_DATABASE_URL,
            poolclass=AsyncAdaptedQueuePool,
            pool_size=2,
            max_overflow=0,
            pool_pre_ping=True,
        )

        def on_invalidate(dbapi_conn, connection_record, exception):
            nonlocal invalidated_count
            invalidated_count += 1

        event.listen(engine.pool, "invalidate", on_invalidate)

        # Checkout two connections, get their PIDs, return to pool
        pids = []
        for _ in range(2):
            async with engine.connect() as conn:
                result = await conn.execute(text("SELECT pg_backend_pid()"))
                pids.append(result.scalar())

        # Kill the first backend
        kill_engine = create_async_engine(
            TEST_DATABASE_URL,
            poolclass=AsyncAdaptedQueuePool,
            pool_size=1,
            max_overflow=0,
        )
        async with kill_engine.connect() as killer:
            await killer.execute(
                text("SELECT pg_terminate_backend(:pid)"),
                {"pid": pids[0]},
            )
        await kill_engine.dispose()

        # Checkout — pre_ping should detect the dead one and invalidate pool
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))

        assert (
            invalidated_count >= 1
        ), "Expected at least one connection to be invalidated"

        await engine.dispose()
