"""One-time migration: Clean up database - drop is_profile_public column and remove invalid activity types."""

import asyncio

from sqlalchemy import text

from core.database import get_engine


async def main():
    """Clean up database: drop unused column and invalid data."""
    engine = get_engine()
    async with engine.begin() as conn:
        # Drop the is_profile_public column
        await conn.execute(
            text("ALTER TABLE users DROP COLUMN IF EXISTS is_profile_public")
        )
        print("✅ Dropped is_profile_public column")
        
        # Delete activities with invalid activity_type values
        result = await conn.execute(
            text("DELETE FROM user_activities WHERE activity_type = 'reflection'")
        )
        print(f"✅ Deleted {result.rowcount} invalid 'reflection' activities")


if __name__ == "__main__":
    asyncio.run(main())
