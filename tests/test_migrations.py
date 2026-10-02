"""Tests for the packaged Alembic config and migration-job runner."""

from __future__ import annotations

from unittest.mock import AsyncMock, call, patch
from uuid import uuid4

import pytest
from alembic.script import ScriptDirectory
from sqlalchemy import text

from learn_to_cloud import migrations
from learn_to_cloud.core.database import Base


@pytest.mark.unit
def test_alembic_config_resolves_packaged_scripts() -> None:
    script = ScriptDirectory.from_config(migrations.alembic_config())

    assert script.get_current_head() is not None


@pytest.mark.unit
@pytest.mark.parametrize("runtime_role", [None, "ltc_api_runtime_test"])
def test_main_upgrades_then_verifies_heads_schema_and_grants(
    monkeypatch: pytest.MonkeyPatch, runtime_role: str | None
) -> None:
    if runtime_role:
        monkeypatch.setenv("POSTGRES_API_RUNTIME_ROLE", runtime_role)
    else:
        monkeypatch.delenv("POSTGRES_API_RUNTIME_ROLE", raising=False)

    with (
        patch.object(migrations, "configure_logging") as configure_logging,
        patch.object(migrations, "command") as command,
        patch.object(
            migrations, "_verify_runtime_grants", new_callable=AsyncMock
        ) as verify_grants,
    ):
        migrations.main()

    configure_logging.assert_called_once_with()
    config = command.upgrade.call_args.args[0]
    assert command.mock_calls == [
        call.upgrade(config, "head"),
        call.current(config, check_heads=True),
        call.check(config),
    ]
    if runtime_role:
        verify_grants.assert_awaited_once_with(runtime_role)
    else:
        verify_grants.assert_not_awaited()


@pytest.mark.integration
@pytest.mark.asyncio
async def test_missing_runtime_grants_reports_each_absent_privilege(
    test_engine,
) -> None:
    role = f"ltc_runtime_test_{uuid4().hex[:12]}"
    tables = sorted(table.name for table in Base.metadata.sorted_tables)
    revoked_table = tables[0]

    async with test_engine.connect() as connection:
        transaction = await connection.begin()
        try:
            await connection.execute(text(f'CREATE ROLE "{role}" NOLOGIN'))
            assert await migrations.missing_runtime_grants(connection, role) == [
                (table, privilege)
                for table in tables
                for privilege in sorted(migrations.RUNTIME_PRIVILEGES)
            ]

            await connection.execute(
                text(
                    "GRANT SELECT, INSERT, UPDATE, DELETE "
                    f'ON ALL TABLES IN SCHEMA public TO "{role}"'
                )
            )
            assert await migrations.missing_runtime_grants(connection, role) == []

            await connection.execute(
                text(f'REVOKE DELETE ON "{revoked_table}" FROM "{role}"')
            )
            assert await migrations.missing_runtime_grants(connection, role) == [
                (revoked_table, "DELETE")
            ]
        finally:
            await transaction.rollback()
