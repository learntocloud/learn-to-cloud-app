"""Alembic migrations bundled with the package, and the deploy-gate runner."""

from __future__ import annotations

import asyncio
import os
from importlib import import_module

from alembic import command
from alembic.config import Config
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection

from learn_to_cloud.core.database import Base
from learn_to_cloud.core.logger import configure_logging
from learn_to_cloud.migrations.connection import create_migration_engine

SCRIPT_LOCATION = "learn_to_cloud:migrations"
RUNTIME_PRIVILEGES = ("SELECT", "INSERT", "UPDATE", "DELETE")

# has_table_privilege is true if *any* listed privilege is held, so check each
# privilege separately.
_MISSING_GRANTS_SQL = text(
    """
    SELECT t.name, p.privilege
    FROM unnest(CAST(:tables AS text[])) AS t(name)
    CROSS JOIN unnest(CAST(:privileges AS text[])) AS p(privilege)
    WHERE NOT has_table_privilege(:role, quote_ident(t.name), p.privilege)
    ORDER BY t.name COLLATE "C", p.privilege COLLATE "C"
    """
)


def alembic_config() -> Config:
    """Return an Alembic config that resolves scripts from the installed package."""
    config = Config()
    config.set_main_option("script_location", SCRIPT_LOCATION)
    return config


async def missing_runtime_grants(
    connection: AsyncConnection, role: str
) -> list[tuple[str, str]]:
    """Return ``(table, privilege)`` pairs the API runtime role lacks."""
    import_module("learn_to_cloud.models")
    result = await connection.execute(
        _MISSING_GRANTS_SQL,
        {
            "role": role,
            "tables": [table.name for table in Base.metadata.sorted_tables],
            "privileges": list(RUNTIME_PRIVILEGES),
        },
    )
    return [(row.name, row.privilege) for row in result]


async def _verify_runtime_grants(role: str) -> None:
    engine = create_migration_engine()
    try:
        async with engine.connect() as connection:
            missing = await missing_runtime_grants(connection, role)
    finally:
        await engine.dispose()
    if missing:
        details = ", ".join(f"{privilege} on {table}" for table, privilege in missing)
        raise RuntimeError(f"API runtime role {role} is missing: {details}")


def main() -> None:
    """Run the migration job's deploy gate.

    Upgrades to head, asserts the database is at the script head(s), asserts
    the live schema matches ``Base.metadata``, then asserts the API runtime role
    can read and write every application table.
    """
    configure_logging()
    config = alembic_config()
    command.upgrade(config, "head")
    command.current(config, check_heads=True)
    command.check(config)
    runtime_role = os.environ.get("POSTGRES_API_RUNTIME_ROLE")
    if runtime_role:
        asyncio.run(_verify_runtime_grants(runtime_role))
