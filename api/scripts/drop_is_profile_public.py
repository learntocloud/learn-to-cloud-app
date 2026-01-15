"""One-time migration: Clean up production database to match local schema."""

import asyncio

from sqlalchemy import text

from core.database import get_engine


async def main():
    """Clean up database to match local schema."""
    engine = get_engine()
    async with engine.begin() as conn:
        # Rename github_submissions to submissions if it exists
        await conn.execute(
            text("ALTER TABLE IF EXISTS github_submissions RENAME TO submissions")
        )
        print("✅ Renamed github_submissions -> submissions")

        # Drop tables that shouldn't exist
        await conn.execute(text("DROP TABLE IF EXISTS checklist_progress CASCADE"))
        print("✅ Dropped checklist_progress")

        await conn.execute(text("DROP TABLE IF EXISTS daily_reflections CASCADE"))
        print("✅ Dropped daily_reflections")

        # Drop the is_profile_public column if it exists
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
