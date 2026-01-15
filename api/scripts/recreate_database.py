"""DANGEROUS: Drop all tables and recreate from scratch.

This will DELETE ALL DATA. Only use in development/pre-launch.
"""

import asyncio

from sqlalchemy import text

from core.database import Base, get_engine
from models import *  # noqa: F401, F403 - Import all models to register them


async def main():
    """Drop all tables and recreate from models."""
    engine = get_engine()

    print("⚠️  WARNING: This will DELETE ALL DATA!")
    print("Dropping all tables...")

    async with engine.begin() as conn:
        # Drop all tables
        await conn.run_sync(Base.metadata.drop_all)
    print("✅ All tables dropped")

    print("Creating tables from models...")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    print("✅ All tables created")

    # Verify
    async with engine.connect() as conn:
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
