"""Find and report duplicate github_username entries in the users table."""

import asyncio

from sqlalchemy import text

from core.database import get_engine


async def main():
    """Find duplicate github usernames."""
    engine = get_engine()
    async with engine.connect() as conn:
        # Find duplicates
        result = await conn.execute(
            text("""
                SELECT github_username, COUNT(*) as cnt, array_agg(id) as user_ids
                FROM users
                WHERE github_username IS NOT NULL
                GROUP BY github_username
                HAVING COUNT(*) > 1
                ORDER BY cnt DESC
            """)
        )
        duplicates = result.fetchall()

        if not duplicates:
            print("✅ No duplicate github_usernames found!")
            return

        print(f"⚠️  Found {len(duplicates)} github_username(s) with duplicates:\n")
        for row in duplicates:
            username, count, user_ids = row
            print(f"  '{username}': {count} users")
            print(f"    User IDs: {user_ids}")
            print()

        print(
            "To fix: Keep the newest user and remove duplicates, or merge their data."
        )
        print("Note: The unique constraint should prevent new duplicates.")


if __name__ == "__main__":
    asyncio.run(main())
