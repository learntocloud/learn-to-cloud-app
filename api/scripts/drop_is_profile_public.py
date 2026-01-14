"""One-time migration: Drop the is_profile_public column from users table."""

import asyncio

from sqlalchemy import text

from core.database import get_engine


async def main():
    """Drop the is_profile_public column if it exists."""
    engine = get_engine()
    async with engine.begin() as conn:
        await conn.execute(
            text("ALTER TABLE users DROP COLUMN IF EXISTS is_profile_public")
        )
    print("✅ Successfully dropped is_profile_public column from users table")


if __name__ == "__main__":
    asyncio.run(main())
