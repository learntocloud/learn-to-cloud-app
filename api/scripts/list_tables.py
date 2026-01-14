"""List all tables in the production database."""

import asyncio

from sqlalchemy import text

from core.database import get_engine


async def main():
    """List all tables."""
    engine = get_engine()
    async with engine.connect() as conn:
        result = await conn.execute(
            text("SELECT table_name FROM information_schema.tables WHERE table_schema='public' ORDER BY table_name")
        )
        tables = [row[0] for row in result.fetchall()]
        print("Tables in database:")
        for t in tables:
            print(f"  - {t}")


if __name__ == "__main__":
    asyncio.run(main())
