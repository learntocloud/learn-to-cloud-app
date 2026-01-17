"""DANGEROUS: Drop all tables and recreate from scratch.

This will DELETE ALL DATA.

Works with both PostgreSQL and SQLite. Intended for local/dev use.
"""

import asyncio

from sqlalchemy import text

# Import models to register them with Base.metadata
import models  # noqa: F401
from core.database import Base, get_engine


async def main():
    """Drop all tables and recreate from models."""
    engine = get_engine()

    print("⚠️  WARNING: This will DELETE ALL DATA!")
    print("Dropping all tables...")

    async with engine.begin() as conn:
        backend = engine.url.get_backend_name()
        if backend == "sqlite":
            # Drop *all* tables in the file, including legacy tables that are
            # no longer part of SQLAlchemy metadata.
            await conn.execute(text("PRAGMA foreign_keys=OFF"))
            result = await conn.execute(
                text(
                    "SELECT name FROM sqlite_master "
                    "WHERE type='table' AND name NOT LIKE 'sqlite_%'"
                )
            )
            table_names = [row[0] for row in result.fetchall()]
            for table_name in table_names:
                await conn.execute(text(f'DROP TABLE IF EXISTS "{table_name}"'))
        else:
            # Drop all tables known to SQLAlchemy
            await conn.run_sync(Base.metadata.drop_all)
    print("✅ All tables dropped")

    print("Creating tables from models...")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    print("✅ All tables created")

    # Verify
    async with engine.connect() as conn:
        backend = engine.url.get_backend_name()
        if backend == "sqlite":
            result = await conn.execute(
                text(
                    "SELECT name FROM sqlite_master "
                    "WHERE type='table' AND name NOT LIKE 'sqlite_%' "
                    "ORDER BY name"
                )
            )
            tables = [row[0] for row in result.fetchall()]
        else:
            result = await conn.execute(
                text(
                    "SELECT table_name FROM information_schema.tables "
                    "WHERE table_schema='public' ORDER BY table_name"
                )
            )
            tables = [row[0] for row in result.fetchall()]

        print(f"\nTables in database: {tables}")


if __name__ == "__main__":
    asyncio.run(main())
