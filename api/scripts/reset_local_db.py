"""Reset local development database to match current models."""

import asyncio
import sys
from pathlib import Path

# Ensure api/ is in Python path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.pool import NullPool


async def reset() -> None:
    admin = create_async_engine(
        "postgresql+asyncpg://postgres:postgres@localhost:5432/postgres",
        poolclass=NullPool,
        isolation_level="AUTOCOMMIT",
    )
    async with admin.connect() as c:
        await c.execute(
            text(
                "SELECT pg_terminate_backend(pid) "
                "FROM pg_stat_activity "
                "WHERE datname = 'learn_to_cloud' AND pid <> pg_backend_pid()"
            )
        )
        await c.execute(text("DROP DATABASE IF EXISTS learn_to_cloud"))
        await c.execute(text("CREATE DATABASE learn_to_cloud"))
        print("Database recreated")
    await admin.dispose()

    # Import models so they register with Base.metadata
    import models as models  # noqa: F811
    from core.database import Base

    engine = create_async_engine(
        "postgresql+asyncpg://postgres:postgres@localhost:5432/learn_to_cloud",
        poolclass=NullPool,
    )
    async with engine.begin() as c:
        await c.run_sync(Base.metadata.create_all)
        # Create alembic_version with wide column (default is varchar(32),
        # too narrow for our descriptive revision IDs)
        await c.execute(text("DROP TABLE IF EXISTS alembic_version"))
        await c.execute(
            text(
                "CREATE TABLE alembic_version ("
                "  version_num varchar(128) NOT NULL, "
                "  CONSTRAINT alembic_version_pkc PRIMARY KEY (version_num)"
                ")"
            )
        )
        await c.execute(
            text(
                "INSERT INTO alembic_version (version_num) "
                "VALUES ('0004_analytics_snapshot_and_indexes')"
            )
        )
        print("Schema created from models")
    await engine.dispose()
    print("Alembic stamped to head")


if __name__ == "__main__":
    asyncio.run(reset())
